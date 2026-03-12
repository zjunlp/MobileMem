# -*- coding: utf-8 -*-
"""
Flask server for interactive trajectory visualization using pyecharts.

This module provides a web-based visualization interface for the process of trajectory synthesis,
allowing users to explore the hierarchical structure of events, graphs, and sessions
through an interactive graph visualization.

See https://flask.palletsprojects.com/en/stable/quickstart/ for more details. 
"""
import os
import threading
from flask import (
    Flask, 
    render_template, 
    request, 
    jsonify,
)
from werkzeug.serving import make_server
from .models import TrajectorySynthesisState


class TrajectoryVisualizationServer:
    """A Flask-based server for interactive trajectory visualization.
    
    This class encapsulates the Flask application and provides methods to start,
    stop, and manage the visualization server. It allows users to explore the 
    hierarchical structure of events, graphs, and sessions through an interactive 
    graph visualization.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 5000,
        template_folder: str | None = None,
    ) -> None:
        """Initialize the trajectory visualization server.
        
        Args:
            host (`str`, defaults to `"0.0.0.0"`):
                The host address to bind the server to.
            port (`int`, defaults to `5000`):
                The port number to bind the server to.
            template_folder (`str | None`, optional):
                The folder containing HTML templates. If None, uses the default
                location in the haste package.
        """
        self._host = host
        self._port = port
        
        # Determine template folder
        if template_folder is None:
            # Default to templates folder in haste directory
            haste_dir = os.path.dirname(os.path.abspath(__file__))
            template_folder = os.path.join(haste_dir, "templates")
        
        self._template_folder = template_folder
        
        # The first argument is the name of the application's module or package. 
        # __name__ is a convenient shortcut for this that is appropriate for most cases. 
        # This is needed so that Flask knows where to look for resources such as templates and static files.
        self._app = Flask(
            __name__,
            template_folder=template_folder,
        )
        # Setting JSON_AS_ASCII = False can make the JSON output more human-readable. 
        self._app.config['JSON_AS_ASCII'] = False
        
        # Global state object
        self._trajectory_state = None
        
        # Server and thread references
        self._server = None
        self._thread = None
        self._is_running = False
        
        # Register routes
        self._register_routes()

    def _register_routes(self) -> None:
        """Register all Flask routes for the application."""
        
        @self._app.route("/")
        def index():
            """Render the main visualization page."""
            # Flask will look for templates in the templates folder.
            return render_template("index.html")

        # Use the route() decorator to tell Flask what URL should trigger our function.
        @self._app.route("/api/graph")
        def get_graph():
            """
            API endpoint to get graph data for visualization.
            
            Query Parameters:
                node_id: str, optional
                    The node ID to visualize.
                expand_messages: str, optional
                    If "true", expand session to show messages.
                    
            Returns:
                JSON response with graph data and metadata.
            """
            if self._trajectory_state is None:
                return jsonify({"error": "Trajectory state not initialized"}), 500
            
            # Flask uses context locals. 
            node_id = request.args.get("node_id", None)
            expand_messages = request.args.get("expand_messages", "false").lower() == "true"
            
            graph_data = self._trajectory_state.get_graph_for_visualization(node_id, expand_messages)
            
            # If it's a dict or list, a response object is created using jsonify().
            return jsonify(
                {
                    "nodes": graph_data["nodes"],
                    "edges": graph_data["edges"],
                    "categories": graph_data["categories"],
                    "current_node_id": graph_data["current_node_id"],
                    "can_expand": graph_data["can_expand"],
                    "can_go_back": graph_data["can_go_back"],
                    "parent_node_id": graph_data["parent_node_id"],
                    "is_message_view": expand_messages,
                }
            )

        @self._app.route("/api/node_details")
        def get_node_details():
            """
            API endpoint to get detailed information about a node.
            
            Query Parameters:
                node_id: str, optional
                    The node ID to get details for.
                    
            Returns:
                JSON response with markdown formatted details.
            """
            if self._trajectory_state is None:
                return jsonify({"error": "Trajectory state not initialized"}), 500
            
            node_id = request.args.get("node_id", None)
            
            graph_data = self._trajectory_state.get_graph_for_visualization(node_id)
            md_details = graph_data["node_details"]
            
            return jsonify(
                {
                    "markdown": md_details,
                    "node_id": graph_data["current_node_id"],
                }
            )

        @self._app.route("/api/navigate")
        def navigate():
            """
            API endpoint for navigation actions.
            
            Query Parameters:
                action: str
                    Navigation action: 'expand', 'back', or 'goto'
                node_id: str, optional
                    Target node ID for 'expand' and 'goto' actions.
                    
            Returns:
                JSON response with new graph data.
            """
            if self._trajectory_state is None:
                return jsonify({"error": "Trajectory state not initialized"}), 500
            
            action = request.args.get("action")
            node_id = request.args.get("node_id", None)
            
            if action == "expand":
                # Get child node ID for the node
                child_id = self._trajectory_state.get_child_node_id(node_id)
                if child_id is not None:
                    return jsonify(
                        {
                            "success": True,
                            "target_node_id": child_id,
                        }
                    )
                else:
                    return jsonify(
                        {
                            "success": False,
                            "message": "No child node found"
                        }
                    )
            
            elif action == "back":
                # Get parent node ID
                graph_data = self._trajectory_state.get_graph_for_visualization(node_id)
                parent_id = graph_data["parent_node_id"]
                if parent_id is not None:
                    return jsonify(
                        {
                            "success": True,
                            "target_node_id": parent_id,
                        }
                    )
                else:
                    return jsonify(
                        {
                            "success": False,
                            "message": "Already at root"
                        }
                    )
            
            elif action == "goto":
                # Navigate to specific node
                return jsonify(
                    {
                        "success": True,
                        "target_node_id": node_id,
                    }
                )
            
            else:
                return jsonify(
                    {
                        "success": False,
                        "message": "Invalid action"
                    }
                )

        @self._app.route("/api/statistics")
        def get_statistics():
            """Get trajectory statistics."""
            if self._trajectory_state is None:
                return jsonify({"error": "Trajectory state not initialized"}), 500
            
            stats = self._trajectory_state.get_statistics()
            return jsonify(stats)

    def set_trajectory_state(self, state: TrajectorySynthesisState) -> None:
        """Set the trajectory state for visualization.
        
        Args:
            state (`TrajectorySynthesisState`):
                The trajectory state to visualize.
        """
        self._trajectory_state = state
        print("Trajectory state is updated for visualization!")
        print(f"  - Person: {state.person.name}")
        print(f"  - Graphs: {len(state.graphs)}")
        print(f"  - Sessions: {len(state.sessions)}")

    def start(self, daemon: bool = False) -> None:
        """Start the Flask server in a background thread.
        
        Args:
            daemon (`bool`, defaults to `False`):
                Whether to run the server thread as a daemon thread.
                If True, the thread will be terminated when the main program exits.
        """
        if self._is_running:
            print(f"⚠️  Trajectory visualization server is already running on http://{self._host}:{self._port}")
            return
        
        # Start Flask server using Werkzeug server for graceful shutdown
        self._server = make_server(self._host, self._port, self._app, threaded=True)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=daemon,
        )
        self._thread.start()
        self._is_running = True
        print(f"✅ Trajectory visualization server started on http://{self._host}:{self._port}")

    def stop(self) -> None:
        """Stop the Flask server."""
        if not self._is_running:
            print("⚠️  Trajectory visualization server is not running")
            return
        
        if self._server is not None:
            print("🛑 Stopping trajectory visualization server...")
            self._server.shutdown()
            self._server = None
        
        self._is_running = False
        self._thread = None
        print("✅ Trajectory visualization server stopped")

    def wait(self) -> None:
        """Wait for the server thread to finish (blocks until stopped)."""
        if self._thread is not None:
            self._thread.join()

    @property
    def is_running(self) -> bool:
        """Check if the server is currently running."""
        return self._is_running

    @property
    def url(self) -> str:
        """Get the server URL."""
        return f"http://{self._host}:{self._port}"

    @property
    def app(self) -> Flask:
        """Get the Flask application instance."""
        return self._app

