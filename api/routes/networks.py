from __future__ import annotations

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from api.models import NetworkConfig, RunParams
from api.sessions import SessionStatus, manager

router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=4)


def _session_or_404(session_id: str):
    session = manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return session


@router.post("/networks", status_code=201)
def create_network(config: NetworkConfig):
    try:
        session = manager.create(config)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"id": session.id, "status": session.status}


@router.get("/networks/{session_id}")
def get_network(session_id: str):
    session = _session_or_404(session_id)
    nodes = [
        {
            **node.model_dump(exclude_none=True),
            "kind": node.type,
        }
        for node in session.config.nodes
    ]
    edges = [
        edge.model_dump()
        for edge in session.config.edges
    ]
    return {
        "id": session_id,
        "status": session.status,
        "nodes": nodes,
        "edges": edges,
    }


@router.delete("/networks/{session_id}", status_code=204)
def delete_network(session_id: str):
    if not manager.delete(session_id):
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")


@router.post("/networks/{session_id}/stop")
def stop_network(session_id: str):
    session = _session_or_404(session_id)
    session.stop()
    return {"status": session.status}


@router.post("/networks/{session_id}/step")
def step_network(session_id: str):
    session = _session_or_404(session_id)
    if session.status == SessionStatus.RUNNING:
        raise HTTPException(status_code=409, detail="Simulation is currently running; stop it first")
    state = session.step()
    return {"state": state, "stats": session.get_stats()}


@router.get("/networks/{session_id}/state")
def get_state(session_id: str):
    session = _session_or_404(session_id)
    return session.get_state()


@router.get("/networks/{session_id}/stats")
def get_stats(session_id: str):
    session = _session_or_404(session_id)
    return session.get_stats()


@router.websocket("/networks/{session_id}/stream")
async def stream_network(websocket: WebSocket, session_id: str):
    session = manager.get(session_id)
    if session is None:
        await websocket.close(code=4004)
        return

    await websocket.accept()

    # Receive run params from client
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
        params = RunParams(**json.loads(raw))
    except (asyncio.TimeoutError, Exception) as exc:
        await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
        await websocket.close()
        return

    if session.status == SessionStatus.RUNNING:
        await websocket.send_text(json.dumps({"type": "error", "message": "Already running"}))
        await websocket.close()
        return

    session.status = SessionStatus.RUNNING
    session._stop_event.clear()
    stream_queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def run_sim():
        """Run simulation in thread, pushing state snapshots to queue."""
        try:
            session.initialize()

            last_push = time.monotonic()
            until = params.until
            interval = params.stream_interval

            while (
                not session.net.sim.scheduler.is_empty()
                and session.net.sim.clock < until
                and not session._stop_event.is_set()
            ):
                session.net.sim.step()
                session.event_count += 1

                now = time.monotonic()
                if now - last_push >= interval:
                    state = session.get_state()
                    stats = session.get_stats()
                    loop.call_soon_threadsafe(
                        stream_queue.put_nowait,
                        {"type": "state", "data": state, "stats": stats},
                    )
                    last_push = now

            if session._stop_event.is_set():
                session.status = SessionStatus.PAUSED
                message_type = "stopped"
            else:
                session.status = SessionStatus.DONE
                message_type = "done"
            final_state = session.get_state()
            final_stats = session.get_stats()
            loop.call_soon_threadsafe(
                stream_queue.put_nowait,
                {"type": message_type, "data": final_state, "stats": final_stats},
            )
        except Exception as exc:
            loop.call_soon_threadsafe(
                stream_queue.put_nowait,
                {"type": "error", "message": str(exc)},
            )

    future = loop.run_in_executor(_executor, run_sim)

    try:
        while True:
            msg = await asyncio.wait_for(stream_queue.get(), timeout=60.0)
            await websocket.send_text(json.dumps(msg))
            if msg["type"] in ("done", "error", "stopped"):
                break
    except (asyncio.TimeoutError, WebSocketDisconnect):
        session.stop()
    finally:
        future.cancel()
        await websocket.close()
