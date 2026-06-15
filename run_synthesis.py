# -*- coding: utf-8 -*-
"""
Run trajectory synthesis with pre-defined persona.

This script runs the KEME trajectory synthesis pipeline using an existing persona
(loaded from a JSON file) and provides visualization through both the trajectory 
visualization server and the AgentScope studio server.
"""
import argparse
import asyncio
import json
import os
import pickle
import signal
from typing import Any

import shortuuid
from agentscope.formatter import OpenAIChatFormatter
from agentscope.message import Msg
from agentscope.model import OpenAIChatModel
from pyngrok import ngrok

from keme.models import (
    Person, 
    TrajectorySynthesisState, 
) 
from keme.toolkits import (
    SynthesisAgent,
    TemporalEventGraphNotebook,
    SessionNotebook,
    SessionGroundingNotebook,
    GraphRefinementNotebook,
    DefaultTemporalEventGraphToHint,
    DefaultSessionToHint,
    DefaultSessionGroundingToHint,
    DefaultGraphRefinementToHint,
) 
from keme.schedulers import ConstantGraphNotebookStateScheduler
from keme.utils import StudioServer, SYSTEM_PROMPT
from keme.traj_server import TrajectoryVisualizationServer


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run KEME trajectory synthesis with pre-defined persona.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    
    # Persona configuration
    parser.add_argument(
        "--persona_path",
        type=str,
        default="person.json",
        help="Path to the persona JSON file.",
    )
    
    # Model configuration
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4.1",
        help="Model name to use for synthesis.",
    )
    parser.add_argument(
        "--api_key",
        type=str,
        default=None,
        help="OpenAI API key. If not provided, uses OPENAI_API_KEY environment variable.",
    )
    parser.add_argument(
        "--api_base",
        type=str,
        default=None,
        help="OpenAI API base URL. If not provided, uses OPENAI_API_BASE environment variable.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=1.0,
        help="Temperature for model generation.",
    )
    
    # Synthesis configuration
    parser.add_argument(
        "--max_events",
        type=int,
        default=15,
        help="Maximum number of events per temporal event graph.",
    )
    parser.add_argument(
        "--min_events",
        type=int,
        default=1,
        help="Minimum number of events per temporal event graph.",
    )
    parser.add_argument(
        "--max_depth",
        type=int,
        default=2,
        help="Maximum depth of the event hierarchy.",
    )
    parser.add_argument(
        "--max_iters",
        type=int,
        default=50,
        help="Maximum iterations for the synthesis agent.",
    )
    parser.add_argument(
        "--parallel_tool_calls",
        action="store_true",
        help="Enable parallel tool calls.",
    )
    parser.add_argument(
        "--compatibility_context_max_tokens",
        type=int,
        default=8000,
        help="Maximum tokens for compatibility context before triggering summarization.",
    )
    parser.add_argument(
        "--grounded_session_subgraph_threshold",
        type=int,
        default=None,
        help=(
            "Threshold on the number of grounded sessions assigned to an event. When an "
            "event's grounded session count exceeds this threshold, the event is not forced "
            "to expand into a single session at the maximum depth."
        ),
    )
    
    # Server configuration
    parser.add_argument(
        "--traj_server_host",
        type=str,
        default="0.0.0.0",
        help="Host for the trajectory visualization server.",
    )
    parser.add_argument(
        "--traj_server_port",
        type=int,
        default=5000,
        help="Port for the trajectory visualization server.",
    )
    parser.add_argument(
        "--studio_url",
        type=str,
        default=None,
        help="URL for the AgentScope studio server. If not provided, studio visualization is disabled.",
    )
    parser.add_argument(
        "--studio_project",
        type=str,
        default="keme",
        help="Project name for the AgentScope studio.",
    )
    
    # Ngrok configuration
    parser.add_argument(
        "--ngrok_authtoken",
        type=str,
        default=None,
        help="Ngrok auth token for public URL. If not provided, uses NGROK_AUTHTOKEN environment variable.",
    )
    parser.add_argument(
        "--disable_ngrok",
        action="store_true",
        help="Disable ngrok tunnel for public access.",
    )
    
    # Output configuration
    parser.add_argument(
        "--output_path",
        type=str,
        default="trajectory_state.pkl",
        help="Path to save the synthesized trajectory state.",
    )
    
    return parser.parse_args()


class SynthesisRunner:
    """Runner class for KEME trajectory synthesis."""

    def __init__(self, args: argparse.Namespace) -> None:
        """Initialize the synthesis runner.
        
        Args:
            args (`argparse.Namespace`):
                Parsed command line arguments.
        """
        self.args = args
        
        # Server instances
        self.traj_server = None
        self.studio_server = None
        self.ngrok_tunnel = None
        
        # State
        self.global_state = None
        self.synthesis_task_cancelled = False
        
        # Set up signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle Ctrl+C signals with two-stage shutdown."""
        if not self.synthesis_task_cancelled:
            # First Ctrl+C: Stop synthesis task, keep servers running
            print("\n⚠️  Synthesis task cancelled. Servers continue running.")
            print("   Press Ctrl+C again to stop all servers.")
            self.synthesis_task_cancelled = True
            # Schedule task cancellation in the event loop
            try:
                loop = asyncio.get_running_loop()
                for task in asyncio.all_tasks(loop):
                    if not task.done():
                        task.cancel()
            except RuntimeError:
                pass
        else:
            # Second Ctrl+C: Stop all servers
            self._shutdown()
            os._exit(0)

    def _shutdown(self) -> None:
        """Shutdown all servers and connections."""
        # Clean up hooks
        self._cleanup_hooks()
        
        if self.traj_server is not None and self.traj_server.is_running:
            self.traj_server.stop()
        
        if self.studio_server is not None:
            print("🛑 Deactivating studio server...")
            self.studio_server.deactivate()
        
        if self.ngrok_tunnel is not None:
            print("🛑 Stopping ngrok tunnel...")
            try:
                ngrok.disconnect(self.ngrok_tunnel.public_url)
            except Exception:
                pass

    def _cleanup_hooks(self) -> None:
        """Clean up registered hooks."""
        try:
            SessionNotebook.remove_class_hook("synthesis_session_hook")
        except ValueError:
            pass
        try:
            TemporalEventGraphNotebook.remove_class_hook("synthesis_graph_hook")
        except ValueError:
            pass
        try:
            GraphRefinementNotebook.remove_class_hook("synthesis_refinement_hook")
        except ValueError:
            pass
        try:
            SessionGroundingNotebook.remove_class_hook("synthesis_grounding_hook")
        except ValueError:
            pass

    def _load_persona(self) -> Person:
        """Load persona from JSON file.
        
        Returns:
            `Person`:
                The loaded persona object.
        
        Raises:
            `FileNotFoundError`:
                If the persona file does not exist.
        """
        if not os.path.exists(self.args.persona_path):
            raise FileNotFoundError(
                f"Persona file '{self.args.persona_path}' is not found. "
                "Please provide a valid persona JSON file."
            )
        
        with open(self.args.persona_path, "r", encoding="utf-8") as f:
            person = Person.model_validate(json.load(f))
        
        print(f"✅ Loaded persona: {person.name}")
        print(f"   - Trajectory: {person.trajectory_start} to {person.trajectory_end}")
        return person

    def _setup_model(self) -> dict[str, Any]:
        """Set up the model and return agent keyword arguments.
        
        Returns:
            `dict[str, Any]`:
                Keyword arguments for the synthesis agent.
        """
        # Get API key and base URL
        api_key = self.args.api_key or os.environ.get("OPENAI_API_KEY")
        api_base = self.args.api_base or os.environ.get("OPENAI_API_BASE")
        
        if not api_key:
            raise ValueError(
                "OpenAI API key is required. Provide via --api_key or OPENAI_API_KEY environment variable."
            )
        
        client_args = {}
        if api_base:
            client_args["base_url"] = api_base
        
        model = OpenAIChatModel(
            model_name=self.args.model,
            api_key=api_key,
            client_args=client_args,
            generate_kwargs={
                "temperature": self.args.temperature,
            },
        )
        
        print(f"✅ Model configured: {self.args.model}")
        print(f"   - Temperature: {self.args.temperature}")
        
        return {
            "model": model,
            "formatter": OpenAIChatFormatter(),
            "max_iters": self.args.max_iters,
            "parallel_tool_calls": self.args.parallel_tool_calls,
        }

    def _setup_servers(self) -> None:
        """Set up visualization servers."""
        # Set up trajectory visualization server
        self.traj_server = TrajectoryVisualizationServer(
            host=self.args.traj_server_host,
            port=self.args.traj_server_port,
        )
        # Set up AgentScope studio server if URL is provided
        if self.args.studio_url:
            try:
                self.studio_server = StudioServer(
                    url=self.args.studio_url,
                    project=self.args.studio_project,
                )
                self.studio_server.activate()
                print(f"✅ Studio server connected: {self.args.studio_url}")
            except Exception as e:
                print(f"⚠️  Failed to connect to studio server: {e}")
                self.studio_server = None

    def _setup_ngrok(self) -> str | None:
        """Set up ngrok tunnel for public access.
        
        Returns:
            `str | None`:
                The public URL if ngrok is enabled and successful, None otherwise.
        """
        if self.args.disable_ngrok:
            return None
        
        # Get ngrok auth token
        ngrok_authtoken = self.args.ngrok_authtoken or os.environ.get("NGROK_AUTHTOKEN")
        
        if not ngrok_authtoken:
            print("⚠️  Ngrok auth token not provided. Public URL will not be available.")
            return None
        
        ngrok.set_auth_token(ngrok_authtoken)
        
        try:
            self.ngrok_tunnel = ngrok.connect(self.args.traj_server_port, bind_tls=True)
            public_url = self.ngrok_tunnel.public_url
            print(f"🌐 Public URL (accessible from anywhere): {public_url}")
            return public_url
        except Exception as e:
            print(f"⚠️  Failed to create ngrok tunnel: {e}")
            return None

    def _register_hooks(self) -> None:
        """Register hooks for state synchronization.
        
        These hooks are triggered when the notebook state changes, allowing us to
        synchronize the global trajectory state with the notebook state.
        """
        # Keep reference to self for use in hooks
        runner = self
        
        def session_notebook_hook(notebook: SessionNotebook) -> None:
            """Hook for session notebook state changes."""
            if notebook.current_session is not None:
                session = notebook.current_session
                if session.id not in runner.global_state.sessions:
                    runner.global_state.add_session(session)
        SessionNotebook.register_class_hook(
            "synthesis_session_hook",
            session_notebook_hook,
        )

        def graph_notebook_hook(notebook: TemporalEventGraphNotebook) -> None:
            """Hook for temporal event graph notebook state changes."""
            graph = notebook.current_graph
            if graph is not None:
                if graph.id not in runner.global_state.graphs:
                    runner.global_state.add_graph(graph)
                else:
                    runner.global_state.refresh_graph(graph.id)
        TemporalEventGraphNotebook.register_class_hook(
            "synthesis_graph_hook",
            graph_notebook_hook,
        )

        def graph_refinement_notebook_hook(notebook: GraphRefinementNotebook) -> None:
            """Hook for graph refinement notebook state changes."""
            state = notebook.current_state
            graph = state.graph
            if graph.id not in runner.global_state.graphs:
                runner.global_state.add_graph(graph)
            else:
                runner.global_state.refresh_graph(graph.id)
        GraphRefinementNotebook.register_class_hook(
            "synthesis_refinement_hook",
            graph_refinement_notebook_hook,
        )

        def session_grounding_notebook_hook(notebook: SessionGroundingNotebook) -> None:
            """Hook for session grounding notebook state changes."""
            graph = notebook.current_graph
            if graph.id not in runner.global_state.graphs:
                runner.global_state.add_graph(graph)
            else:
                runner.global_state.refresh_graph(graph.id)
        SessionGroundingNotebook.register_class_hook(
            "synthesis_grounding_hook",
            session_grounding_notebook_hook,
        ) 

    async def run(self) -> None:
        """Run the synthesis pipeline."""
        # Load persona
        person = self._load_persona()
        
        # Set up model
        agent_kwargs = self._setup_model()
        
        # Initialize global state
        self.global_state = TrajectorySynthesisState(person=person)
        
        # Set up servers
        self._setup_servers()
        
        # Start trajectory visualization server
        self.traj_server.set_trajectory_state(self.global_state)
        self.traj_server.start(daemon=False)
        
        # Set up ngrok
        public_url = self._setup_ngrok()
        
        # Register hooks
        self._register_hooks()
        
        # Create synthesis scheduler
        synthesis_scheduler = ConstantGraphNotebookStateScheduler(
            min_events=self.args.min_events,
            max_events=self.args.max_events,
            max_depth=self.args.max_depth,
            grounded_session_subgraph_threshold=self.args.grounded_session_subgraph_threshold,
        )
        
        print(f"✅ Scheduler configured:")
        print(f"   - Min events: {self.args.min_events}")
        print(f"   - Max events: {self.args.max_events}")
        print(f"   - Max depth: {self.args.max_depth}")
        
        # Create root agent
        root_agent_name = f"agent_{shortuuid.uuid()}"
        graph_notebook = TemporalEventGraphNotebook(
            person,
            root_agent_name,
            level=0,
            scheduler=synthesis_scheduler,
            graph_to_hint=DefaultTemporalEventGraphToHint(),
            session_to_hint=DefaultSessionToHint(),
            graph_refinement_to_hint=DefaultGraphRefinementToHint(),
            session_grounding_to_hint=DefaultSessionGroundingToHint(),
            compatibility_context_max_tokens=self.args.compatibility_context_max_tokens,
            **agent_kwargs,
        )
        root_agent = SynthesisAgent(
            name=root_agent_name,
            sys_prompt=SYSTEM_PROMPT.format(agent_id=root_agent_name),
            notebook=graph_notebook,
            **agent_kwargs,
        )
        
        print("\n" + "=" * 60)
        print("🚀 Starting trajectory synthesis...")
        print("=" * 60 + "\n")
        
        # Create synthesis task
        synthesis_task = asyncio.create_task(
            root_agent(
                msg=Msg(
                    "user",
                    synthesis_scheduler.get_task_instruction(
                        person,
                        level=0,
                        instruction_type="temporal_event_graph",
                    ),
                    "user",
                ),
            )
        )
        
        try:
            _ = await synthesis_task
            
            # Save trajectory state after synthesis completes
            with open(self.args.output_path, "wb") as f:
                pickle.dump(self.global_state, f)
            print(f"\n💾 Trajectory state saved to {self.args.output_path}")
            
        except asyncio.CancelledError:
            pass
        except KeyboardInterrupt:
            pass
        
        # Print status
        if self.synthesis_task_cancelled:
            print("\n⏸️  Synthesis task cancelled. Servers continue running.")
        else:
            print("\n✅ Synthesis completed. Servers continue running.")
        
        print(f"   Local: http://{self.args.traj_server_host}:{self.args.traj_server_port}")
        if public_url:
            print(f"   Public: {public_url}")
        print("   Press Ctrl+C to stop all servers.")
        
        # Keep the main thread alive
        try:
            self.traj_server.wait()
        except KeyboardInterrupt:
            pass


async def main() -> None:
    """Main entry point."""
    args = parse_args()
    
    print("\n" + "=" * 60)
    print("KEME: Knowledge-Guided Experience Synthesis for Evolving Memory")
    print("=" * 60 + "\n")
    
    runner = SynthesisRunner(args) 
    await runner.run()


if __name__ == "__main__":
    asyncio.run(main())

