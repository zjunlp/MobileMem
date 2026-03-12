"""All functions in this file are copied from agentscope library."""
# -*- coding: utf-8 -*-
import asyncio
import functools
import inspect
import os
from agentscope.message import Msg
from agentscope.agent import AgentBase
from datetime import datetime
from copy import deepcopy
import shortuuid 
import requests 
import socketio
import types
import time 
from typing import Callable, Any


def get_timestamp(add_random_suffix: bool = False) -> str:
    """Get the current timestamp in the format YYYY-MM-DD HH:MM:SS.sss."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    if add_random_suffix:
        # Add a random suffix to the timestamp
        timestamp += f"_{os.urandom(3).hex()}"

    return timestamp


async def is_async_func(func: Callable) -> bool:
    """Check if the given function is an async function, including
    coroutine functions, async generators, and coroutine objects."""
    return (
        inspect.iscoroutinefunction(func)
        or inspect.isasyncgenfunction(func)
        or isinstance(func, types.CoroutineType)
        or isinstance(func, types.GeneratorType)
        and asyncio.iscoroutine(func)
        or isinstance(func, functools.partial)
        and await is_async_func(func.func)
    )


async def execute_async_or_sync_func(
    func: Callable,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Execute an async or sync function based on its type.

    Args:
        func (`Callable`):
            The function to be executed, which can be either async or sync.
        *args (`Any`):
            Positional arguments to be passed to the function.
        **kwargs (`Any`):
            Keyword arguments to be passed to the function.

    Returns:
        `Any`:
            The result of the function execution.
    """
    if await is_async_func(func):
        return await func(*args, **kwargs)

    return func(*args, **kwargs)


class StudioServer: 
    """A client for connecting to and interacting with the AgentScope Studio server."""

    def __init__(
        self, 
        url: str = "http://localhost:3000", 
        project: str = "experiment", 
        num_messages: int = 100000, 
    ) -> None: 
        """Initialize the StudioServer client and establish connection.

        Args:
            url (`str`, defaults to `"http://localhost:3000"`):
                The base URL of the studio server.
            project (`str`, defaults to `"experiment"`):
                The project name to associate with the runs.
            num_messages (`int`, defaults to `100000`):
                The maximum number of unique messages per run before 
                automatically creating a new run.
        """
        self._url = url 
        self._project= project
        self._run_id = f"run_{shortuuid.uuid()}"
        self._run_counter = 0 
        self._pid = os.getpid()
        self._num_messages = num_messages 
        self._old_replay_ids = set() 
        self._sio_client = None

    def _register_run(self) -> None:
        """Register a new run with the studio server."""
        response = requests.post(
            f"{self._url}/trpc/registerRun", 
            json={
                "id": self._run_id,
                "project": self._project,
                "name": f"{self._run_counter + 1}th_run",
                "timestamp": get_timestamp(),
                "pid": self._pid,
                "status": "running",
                "run_dir": "", 
            }
        )
        response.raise_for_status()
        self._run_counter += 1 
    
    def push_message(
        self, 
        reply_id: str,
        reply_name: str,
        reply_role: str,
        msg: Msg
    ) -> None: 
        """Push a message to the studio server.

        This method sends a message to the server and handles automatic run rotation
        when the message limit is reached.

        Args:
            reply_id (`str`):
                The unique identifier for this reply.
            reply_name (`str`):
                The replay name.
            reply_role (`str`):
                The role of the message sender.
            msg (`Msg`):
                The message object to push to the server.
        """
        if self._sio_client is None or not self._sio_client.connected:
            raise RuntimeError("Studio server is not connected. Please activate the studio server first.")

        if reply_id not in self._old_replay_ids and len(self._old_replay_ids) == self._num_messages:
            response = self._sio_client.call(
                "deleteRuns",
                [self._run_id],
                namespace="/client",
            )
            if not response["success"]:
                raise RuntimeError(response["message"])
            self._old_replay_ids.clear() 
            self._register_run() 
        
        response = requests.post(
            f"{self._url}/trpc/pushMessage",
            json={
                "runId": self._run_id,
                "replyId": reply_id,
                "name": reply_name,
                "role": reply_role,
                "msg": msg.to_dict(),
            },
        )
        response.raise_for_status()

        self._old_replay_ids.add(reply_id)
    
    def _pre_print_hook(
        self, 
        agent: AgentBase,
        kwargs: dict[str, Any]
    ) -> None:
        """The pre-print hook to forward agent messages to the studio.
        
        This hook is registered with AgentBase to intercept messages before they 
        are printed, allowing them to be forwarded to the studio server for 
        visualization.

        Args:
            agent (`AgentBase`):
                The agent instance that is printing the message.
            kwargs (`dict[str, Any]`):
                The input arguments of the pre-print hook, containing the message 
                and other metadata.
        """
        # Note that `kwargs` is a deep copy of the input arguments
        msg = kwargs["msg"]
        msg_copy = deepcopy(msg)

        if isinstance(msg.content, list):
            for i, block in enumerate(msg_copy.content):
                if block["type"] == "tool_use": 
                    # See https://github.com/mangiucugna/json_repair/issues/159
                    # After the model's output is repaired, the block contained in the message may be invalid
                    if isinstance(block["input"], list): 
                        if kwargs["last"]:
                            raise ValueError(
                                "Invalid tool use block in the last chunk: expected `input` to be a "
                                "dictionary (complete function arguments), but got a list. In streaming "
                                "output, only intermediate chunks may have list-type `input` fields. "
                                "The final chunk must contain the complete dictionary of function arguments."
                            )
                        msg.content[i]["input"] = {
                            item: "" 
                            for item in block["input"] 
                        } 
        
        if hasattr(self, "_reply_id"):
            reply_id = getattr(agent, "_reply_id")
        else:
            reply_id = shortuuid.uuid()

        n_retry = 0
        while True:
            try:
                self.push_message(
                    reply_id,
                    reply_id,
                    "assistant",
                    msg,
                )
                break
            except Exception as e:
                if n_retry < 3:
                    n_retry += 1
                    time.sleep(1)
                    continue

                raise e from None
    
    def activate(self) -> None:
        """Activate the studio server integration.
        
        This method enables the automatic forwarding of agent messages to the studio server.
        """
        if self._sio_client is None or not self._sio_client.connected:
            self._sio_client = socketio.Client()
            self._sio_client.connect(self._url, namespaces=["/client"])
            # Note: Reconnecting after deactivate() will reuse the same run ID and increment
            # the run counter. Previous runs registered during earlier activate() calls will
            # be overwritten automatically.
            self._register_run()

        AgentBase.register_class_hook(
            "pre_print",
            "as_studio_forward_message_pre_print_hook",
            self._pre_print_hook,
        )
    
    def deactivate(self) -> None:
        """Deactivate the studio server integration.
        
        This method stops the automatic forwarding of agent messages to the studio server.
        """
        AgentBase.remove_class_hook(
            "pre_print",
            "as_studio_forward_message_pre_print_hook",
        )
        if self._sio_client is not None and self._sio_client.connected:
            self._sio_client.disconnect()
