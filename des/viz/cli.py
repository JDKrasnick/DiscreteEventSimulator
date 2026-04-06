from __future__ import annotations

from typing import TYPE_CHECKING

import networkx as nx
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from des.network.network import QueueingNetwork


def _build_topology_panel(net: QueueingNetwork) -> Panel:
    graph = net.graph
    lines: list[str] = []

    # Topological order so the diagram reads left-to-right
    try:
        order = list(nx.topological_sort(graph))
    except nx.NetworkXUnfeasible:
        order = list(graph.nodes)

    # Build adjacency rows: "src --0.7--> dst"
    seen_edges: set[tuple[str, str]] = set()
    for src in order:
        for dst, data in graph[src].items():
            if (src, dst) in seen_edges:
                continue
            seen_edges.add((src, dst))
            weight = data.get("weight", 1.0)
            kind_src = graph.nodes[src].get("kind", "?")
            kind_dst = graph.nodes[dst].get("kind", "?")

            label_src = _node_label(src, kind_src)
            label_dst = _node_label(dst, kind_dst)
            prob_str = f"{weight:.2f}" if weight != 1.0 else "───"
            lines.append(f"  {label_src}  ──{prob_str}──▶  {label_dst}")

    body = "\n".join(lines) if lines else "  (empty)"
    return Panel(body, title="[bold]Network Topology[/bold]", border_style="blue")


def _node_label(node_id: str, kind: str) -> str:
    icons = {"source": "◉", "server": "▣", "sink": "◎"}
    icon = icons.get(kind, "?")
    return f"{icon} {node_id}"


def _status_color(busy: int, c: int) -> str:
    ratio = busy / c
    if ratio == 0:
        return "dim"
    if ratio < 0.8:
        return "green"
    if ratio < 1.0:
        return "yellow"
    return "red"


def _build_stats_table(net: QueueingNetwork, clock: float, until: float) -> Table:
    table = Table(show_header=True, header_style="bold magenta", box=None, padding=(0, 1))
    table.add_column("Node", style="cyan", min_width=12)
    table.add_column("Kind", min_width=7)
    table.add_column("Servers", justify="center", min_width=8)
    table.add_column("Queue", justify="right", min_width=6)
    table.add_column("ρ", justify="right", min_width=6)
    table.add_column("W (mean)", justify="right", min_width=9)
    table.add_column("Wq (mean)", justify="right", min_width=9)

    graph = net.graph

    try:
        order = list(nx.topological_sort(graph))
    except nx.NetworkXUnfeasible:
        order = list(graph.nodes)

    for node_id in order:
        kind = graph.nodes[node_id].get("kind", "?")

        if kind == "source":
            sources = [s for s in net._sources if s.node_id == node_id]
            src = sources[0] if sources else None
            rate_str = f"λ={graph.nodes[node_id].get('arrival_rate', '?')}"
            table.add_row(node_id, "source", rate_str, "—", "—", "—", "—")

        elif kind == "server":
            server = net._servers.get(node_id)
            if server is None:
                continue
            c = server.c
            busy = server._busy_servers
            qlen = server.queue_length
            util = server.utilization
            color = _status_color(busy, c)
            summary = server.collector.summary(clock)
            W = summary["W"]
            Wq = summary["Wq"]
            W_str = f"{W:.3f}" if isinstance(W, float) and W > 0 else "—"
            Wq_str = f"{Wq:.3f}" if isinstance(Wq, float) and Wq > 0 else "—"
            table.add_row(
                node_id,
                "server",
                f"[{color}]{busy}/{c}[/{color}]",
                str(qlen),
                f"[{color}]{util:.2f}[/{color}]",
                W_str,
                Wq_str,
            )

        elif kind == "sink":
            sink = net._sinks.get(node_id)
            count = sink.count if sink else 0
            table.add_row(node_id, "sink", "—", "—", "—", f"{count} done", "—")

    return table


def _build_config_panel(net: QueueingNetwork) -> Panel:
    table = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 1))
    table.add_column("Node", style="cyan", min_width=14)
    table.add_column("Kind", min_width=7)
    table.add_column("Config", min_width=30)

    graph = net.graph
    try:
        order = list(nx.topological_sort(graph))
    except nx.NetworkXUnfeasible:
        order = list(graph.nodes)

    for node_id in order:
        kind = graph.nodes[node_id].get("kind", "?")

        if kind == "source":
            src = next((s for s in net._sources if s.node_id == node_id), None)
            if src is None:
                continue
            custom = getattr(src, "_inter_arrival_fn", None)
            default_fn = f"Exp(λ={src.arrival_rate})"
            # detect if user passed a custom fn by checking __name__ vs lambda default
            fn_name = getattr(custom, "__name__", "")
            arrival_str = default_fn if fn_name == "<lambda>" else f"custom ({fn_name})"
            cls_str = f"  class={src.customer_class}" if src.customer_class else ""
            table.add_row(node_id, "source", f"arrivals: {arrival_str}{cls_str}")

        elif kind == "server":
            server = net._servers.get(node_id)
            if server is None:
                continue
            custom = getattr(server, "_service_time_fn", None)
            fn_name = getattr(custom, "__name__", "")
            svc_str = f"Exp(μ={server.service_rate})" if fn_name == "<lambda>" else f"custom ({fn_name})"
            table.add_row(node_id, "server", f"c={server.c}  service: {svc_str}  policy: FCFS")

        elif kind == "sink":
            table.add_row(node_id, "sink", "—")

    return Panel(table, title="[bold]Network Config[/bold]", border_style="cyan")


def _build_progress(clock: float, until: float) -> Text:
    pct = min(clock / until, 1.0) * 100
    bar_width = 40
    filled = int(bar_width * pct / 100)
    bar = "█" * filled + "░" * (bar_width - filled)
    return Text(f"  t = {clock:>10.2f}   [{bar}]  {pct:5.1f}%", style="white")


def make_refresh_callback(net: QueueingNetwork, live: Live, until: float, topology_panel: Panel):
    def on_refresh(clock: float, until: float) -> None:
        stats_table = _build_stats_table(net, clock, until)
        progress_text = _build_progress(clock, until)

        layout = Layout()
        layout.split_column(
            Layout(topology_panel, name="topology", size=len(net.graph.edges) + 4),
            Layout(Panel(progress_text, border_style="dim"), name="progress", size=3),
            Layout(Panel(stats_table, title="[bold]Live Statistics[/bold]", border_style="green"), name="stats"),
        )
        live.update(layout)

    return on_refresh


def run_with_cli(net: QueueingNetwork, until: float, refresh_interval: float = 10.0) -> None:
    console = Console()
    topology_panel = _build_topology_panel(net)
    config_panel = _build_config_panel(net)
    console.print(config_panel)

    with Live(console=console, refresh_per_second=4, screen=False) as live:
        callback = make_refresh_callback(net, live, until, topology_panel)

        net.validate()
        for source in net._sources:
            source.start()
        net.sim.run(until=until, on_refresh=callback, refresh_interval=refresh_interval)

    # Final stats table after simulation ends
    console.print()
    console.print(topology_panel)
    final_table = _build_stats_table(net, net.sim.clock, until)
    console.print(Panel(final_table, title="[bold green]Final Statistics[/bold green]", border_style="green"))
    console.print(f"  Simulation ended at t = {net.sim.clock:.2f}", style="dim")
