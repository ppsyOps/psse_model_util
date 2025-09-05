"""
one_line_diagram.py - Enhanced One-Line Diagram Generator for PSSE Models

This module provides an interactive one-line diagram visualization for power system models
using Dash and Cytoscape.js. It supports:
- Custom symbols for different equipment types (buses, transformers, generators, loads)
- Expandable/collapsible nodes for hierarchical data
- Persistent layout that remembers node positions
- Interactive features like zooming, panning, and tooltips
"""

import os
import json
import dash
from dash import html, dcc, callback, Output, Input, State, no_update
import dash_cytoscape as cyto
import networkx as nx
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any, Union
from pathlib import Path
from dataclasses import dataclass, field
import logging
from psse_model_util.common.logging_config import setup_logger
from psse_model_util.model import Model

# Configure logging
logger = setup_logger(__name__)
# logger = logging.getLogger(__name__)

# Custom node styles for different equipment types
NODE_STYLES = {
    'bus': {
        'shape': 'ellipse',
        'background-color': '#2B7CE9',  # Blue
        'width': 40,
        'height': 40,
    },
    'generator': {
        'shape': 'triangle',
        'background-color': '#FFA500',  # Orange
        'width': 50,
        'height': 50,
    },
    'load': {
        'shape': 'rectangle',
        'background-color': '#28A745',  # Green
        'width': 50,
        'height': 30,
    },
    'transformer': {
        'shape': 'diamond',
        'background-color': '#6F42C1',  # Purple
        'width': 50,
        'height': 50,
    },
    'shunt': {
        'shape': 'octagon',
        'background-color': '#DC3545',  # Red
        'width': 40,
        'height': 40,
    },
    'default': {
        'shape': 'ellipse',
        'background-color': '#6C757D',  # Gray
        'width': 30,
        'height': 30,
    }
}

# Default edge style
EDGE_STYLE = {
    'width': 2,
    'line-color': '#666666',
    'target-arrow-color': '#666666',
    'target-arrow-shape': 'triangle',
    'curve-style': 'bezier',
}

@dataclass
class OneLineDiagram:
    """
    A class to generate and manage interactive one-line diagrams for power system models.
    
    Attributes:
        model: The PSSE model to visualize
        layout_dir: Directory to store layout configurations
        show_isolated_nodes: Whether to show nodes with no connections
        show_labels: Whether to show node labels
        node_size: Base size for nodes
        edge_width: Width of edges
        selected_node: Currently selected node
        node_positions: Dictionary to store node positions
    """
    model: Model
    layout_dir: Path = Path("./layouts")
    show_isolated_nodes: bool = False
    show_labels: bool = True
    node_size: int = 40
    edge_width: int = 2
    selected_node: Optional[str] = None
    node_positions: Dict[str, Dict[str, float]] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize the diagram with default values and create layout directory."""
        self.layout_dir.mkdir(parents=True, exist_ok=True)
        self.elements = []
        self.stylesheet = self._get_default_stylesheet()
    
    def _get_default_stylesheet(self) -> List[Dict]:
        """Generate the default stylesheet for the diagram."""
        return [
            # Default node style
            {
                'selector': 'node',
                'style': {
                    'content': 'data(label)' if self.show_labels else '',
                    'text-valign': 'center',
                    'text-halign': 'center',
                    'color': 'white',
                    'font-size': '12px',
                    'font-weight': 'bold',
                    'text-outline-width': '2px',
                    'text-outline-color': '#000',
                    'overlay-opacity': 0,
                    'text-wrap': 'wrap',
                    'text-max-width': '100px',
                }
            },
            # Default edge style
            {
                'selector': 'edge',
                'style': {
                    'label': 'data(label)',
                    'width': str(self.edge_width),
                    'line-color': EDGE_STYLE['line-color'],
                    'target-arrow-color': EDGE_STYLE['target-arrow-color'],
                    'target-arrow-shape': EDGE_STYLE['target-arrow-shape'],
                    'curve-style': EDGE_STYLE['curve-style'],
                    'font-size': '10px',
                    'text-outline-width': '2px',
                    'text-outline-color': '#fff',
                    'text-margin-y': '-10px',
                }
            },
            # Styles for different node types
            *[
                {
                    'selector': f'node[type = "{node_type}"]',
                    'style': {
                        'shape': style['shape'],
                        'background-color': style['background-color'],
                        'width': style['width'],
                        'height': style['height'],
                    }
                }
                for node_type, style in NODE_STYLES.items()
            ],
            # Style for selected node
            {
                'selector': ':selected',
                'style': {
                    'border-width': '3px',
                    'border-color': '#FFD700',  # Gold
                    'border-style': 'solid'
                }
            },
            # Style for hovered node
            {
                'selector': 'node:active',
                'style': {
                    'overlay-opacity': 0.1,
                    'overlay-color': '#FFD700',
                    'overlay-padding': '10px'
                }
            }
        ]
    
    def _get_node_style(self, node_type: str) -> Dict:
        """Get the style for a specific node type."""
        return NODE_STYLES.get(node_type.lower(), NODE_STYLES['default'])
    
    def _get_node_elements(self) -> List[Dict]:
        """Convert model buses and equipment to node elements."""
        elements = []
        
        # Calculate positions in a grid layout
        bus_count = len(self.model.network.bus)
        grid_size = int(bus_count ** 0.5) + 1
        node_spacing = 150  # pixels between nodes
        
        # Add buses with calculated positions
        for idx, (_, bus) in enumerate(self.model.network.bus.iterrows()):
            bus_id = f"bus_{bus['i']}"
            
            # Calculate grid position
            row = idx // grid_size
            col = idx % grid_size
            
            # Get saved position or calculate new one
            if bus_id in self.node_positions:
                position = self.node_positions[bus_id]
            else:
                position = {
                    'x': 100 + col * node_spacing,
                    'y': 100 + row * node_spacing
                }
            
            elements.append({
                'data': {
                    'id': bus_id,
                    'label': f"{bus['i']}",
                    'type': 'bus',
                    'voltage': bus.get('baskv', 0),
                    'area': bus.get('area', ''),
                    'zone': bus.get('zone', ''),
                    'name': bus.get('name', ''),
                },
                'position': position,
                'classes': 'bus-node',
                'grabbable': True,
                'selectable': True,
            })
        
        # Add generators
        if hasattr(self.model.network, 'generator'):
            for _, gen in self.model.network.generator.iterrows():
                gen_id = f"gen_{gen['i']}_{gen['id']}"
                bus_id = f"bus_{gen['i']}"
                elements.append({
                    'data': {
                        'id': gen_id,
                        'label': f"Gen {gen['i']}:{gen['id']}",
                        'parent': bus_id,
                        'type': 'generator',
                        'pg': gen.get('pg', 0),
                        'qg': gen.get('qg', 0),
                        'pt': gen.get('pt', 0),
                        'pb': gen.get('pb', 0),
                    },
                    'classes': 'generator-node',
                    'grabbable': True,
                    'selectable': True,
                })
        
        # Add loads
        if hasattr(self.model.network, 'load'):
            for _, load in self.model.network.load.iterrows():
                load_id = f"load_{load['i']}_{load['id']}"
                bus_id = f"bus_{load['i']}"
                elements.append({
                    'data': {
                        'id': load_id,
                        'label': f"Load {load['i']}:{load['id']}",
                        'parent': bus_id,
                        'type': 'load',
                        'pl': load.get('pl', 0),
                        'ql': load.get('ql', 0),
                    },
                    'classes': 'load-node',
                    'grabbable': True,
                    'selectable': True,
                })
        
        return elements
    
    def _get_edge_elements(self) -> List[Dict]:
        """Convert model branches to edge elements."""
        elements = []
        
        # Add AC lines
        if hasattr(self.model.network, 'acline'):
            for _, line in self.model.network.acline.iterrows():
                from_bus = f"bus_{line['i']}"
                to_bus = f"bus_{line['j']}"
                edge_id = f"line_{line['i']}_{line['j']}_{line['ckt']}"
                
                elements.append({
                    'data': {
                        'id': edge_id,
                        'source': from_bus,
                        'target': to_bus,
                        'label': f"{line['i']}-{line['j']} ({line['ckt']})",
                        'type': 'line',
                        'r': line.get('r', 0),
                        'x': line.get('x', 0),
                        'b': line.get('b', 0),
                        'ratea': line.get('ratea', 0),
                        'rateb': line.get('rateb', 0),
                        'ratec': line.get('ratec', 0),
                    },
                    'classes': 'ac-line',
                    'selectable': True,
                })
        
        # Add transformers
        if hasattr(self.model.network, 'transformer'):
            for _, xfmr in self.model.network.transformer.iterrows():
                from_bus = f"bus_{xfmr['i']}"
                to_bus = f"bus_{xfmr['j']}"
                edge_id = f"xfmr_{xfmr['i']}_{xfmr['j']}_{xfmr['k']}_{xfmr['ckt']}"
                
                elements.append({
                    'data': {
                        'id': edge_id,
                        'source': from_bus,
                        'target': to_bus,
                        'label': f"Xfmr {xfmr['i']}-{xfmr['j']} ({xfmr['ckt']})",
                        'type': 'transformer',
                        'r1-2': xfmr.get('r1-2', 0),
                        'x1-2': xfmr.get('x1-2', 0),
                        'windv1': xfmr.get('windv1', 0),
                        'windv2': xfmr.get('windv2', 0),
                    },
                    'classes': 'transformer-line',
                    'selectable': True,
                })
        
        return elements
    
    def _get_compound_elements(self) -> List[Dict]:
        """Create compound node structures for buses with equipment."""
        elements = []
        
        # Group equipment by bus
        bus_equipment = {}
        for element in self.elements:
            if 'parent' in element['data']:
                parent = element['data']['parent']
                if parent not in bus_equipment:
                    bus_equipment[parent] = []
                bus_equipment[parent].append(element)
        
        # Create compound nodes for buses with equipment
        for bus_id, equipment in bus_equipment.items():
            if len(equipment) > 1:  # Only create compound if bus has multiple equipment
                elements.append({
                    'data': {
                        'id': f"compound_{bus_id}",
                        'label': f"Bus {bus_id.split('_')[-1]}",
                        'type': 'compound',
                    },
                    'classes': 'compound-node',
                    'grabbable': False,
                    'selectable': False,
                })
                
                # Update parent references
                for eq in equipment:
                    eq['data']['parent'] = f"compound_{bus_id}"
        
        return elements
    
    def _get_tooltip(self, element: Dict) -> str:
        """Generate HTML tooltip for an element."""
        data = element['data']
        element_type = data.get('type', '')
        
        if element_type == 'bus':
            return (
                f"<b>Bus {data.get('label', '')}</b><br>"
                f"Voltage: {data.get('voltage', 'N/A')} kV<br>"
                f"Area: {data.get('area', 'N/A')}<br>"
                f"Zone: {data.get('zone', 'N/A')}"
            )
        elif element_type == 'generator':
            return (
                f"<b>Generator {data.get('label', '')}</b><br>"
                f"P: {data.get('pg', 'N/A')} MW<br>"
                f"Q: {data.get('qg', 'N/A')} MVar"
            )
        elif element_type == 'load':
            return (
                f"<b>Load {data.get('label', '')}</b><br>"
                f"P: {data.get('pl', 'N/A')} MW<br>"
                f"Q: {data.get('ql', 'N/A')} MVar"
            )
        elif element_type in ['line', 'transformer']:
            return (
                f"<b>{'Line' if element_type == 'line' else 'Transformer'} {data.get('label', '')}</b><br>"
                f"From: {data['source'].replace('bus_', '')} → To: {data['target'].replace('bus_', '')}<br>"
                f"R: {data.get('r', 'N/A')} pu | X: {data.get('x', 'N/A')} pu"
            )
        return ""
    
    def _save_layout(self, filename: str = None) -> None:
        """Save the current node positions to a JSON file."""
        if not filename:
            filename = f"{self.model.name.replace(' ', '_').lower()}_layout.json"
        
        layout_path = self.layout_dir / filename
        with open(layout_path, 'w') as f:
            json.dump(self.node_positions, f, indent=2)
    
    def _load_layout(self, filename: str = None) -> bool:
        """Load node positions from a JSON file."""
        if not filename:
            filename = f"{self.model.name.replace(' ', '_').lower()}_layout.json"
        
        layout_path = self.layout_dir / filename
        if layout_path.exists():
            with open(layout_path, 'r') as f:
                self.node_positions = json.load(f)
            return True
        return False
    
    def create_diagram(self) -> cyto.Cytoscape:
        """Create the interactive one-line diagram."""
        # Load saved layout if available
        self._load_layout()
        
        # Generate elements
        self.elements = self._get_node_elements() + self._get_edge_elements()
        
        # Add compound nodes if needed
        self.elements.extend(self._get_compound_elements())
        
        # Create the Cytoscape component
        return cyto.Cytoscape(
            id='one-line-diagram',
            elements=self.elements,
            layout={
                'name': 'preset',  # Use preset positions
                'animate': True,
                'fit': True,
                'padding': 10,
                'spacingFactor': 1.5,
            },
            style={
                'width': '100%',
                'height': '800px',
                'background-color': '#f8f9fa',
                'border': '1px solid #dee2e6',
                'border-radius': '4px',
            },
            stylesheet=self.stylesheet,
            userZoomingEnabled=True,
            userPanningEnabled=True,
            boxSelectionEnabled=True,
            autounselectify=False,
            minZoom=0.1,
            maxZoom=5.0,
            # motionBlur=False,
            wheelSensitivity=0.2,
        )
    
    def get_app_layout(self) -> html.Div:
        """Get the complete Dash app layout for the one-line diagram."""
        return html.Div([
            html.Div([
                html.H1(f"One-Line Diagram: {self.model.name}", className="text-center my-3"),
                
                # Controls
                html.Div([
                    html.Div([
                        html.Label('Show Labels:', className="me-2"),
                        dcc.Dropdown(
                            id='label-visibility',
                            options=[
                                {'label': 'All', 'value': 'all'},
                                {'label': 'Buses Only', 'value': 'buses'},
                                {'label': 'None', 'value': 'none'},
                            ],
                            value='all',
                            clearable=False,
                            className="d-inline-block w-auto"
                        ),
                    ], className="me-3 d-inline-block"),
                    
                    html.Div([
                        html.Label('Node Size:', className="me-2"),
                        dcc.Slider(
                            id='node-size-slider',
                            min=10,
                            max=100,
                            step=5,
                            value=self.node_size,
                            marks={i: str(i) for i in range(10, 101, 10)},
                            className="d-inline-block",
                            tooltip={"placement": "bottom", "always_visible": True}
                        ),
                    ], className="me-3 d-inline-block w-25"),
                    
                    html.Button('Reset Layout', id='reset-layout', className="btn btn-outline-secondary me-2"),
                    html.Button('Save Layout', id='save-layout', className="btn btn-primary"),
                    
                    # Node info panel (initially hidden)
                    html.Div(id='node-info', className="mt-3 p-3 bg-light rounded", style={'display': 'none'}),
                ], className="mb-3 p-3 bg-light rounded"),
                
                # Main diagram
                self.create_diagram(),
                
                # Hidden div to store node positions
                dcc.Store(id='node-positions'),
                
                # Hidden div to store selected node
                dcc.Store(id='selected-node'),
                
            ], className="container-fluid py-3"),
            
            # Tooltip
            dcc.Tooltip(id='cytoscape-tooltip'),
        ])
    
    def register_callbacks(self, app: dash.Dash) -> None:
        """Register all necessary callbacks for the diagram."""
        @app.callback(
            Output('cytoscape-tooltip', 'show'),
            Output('cytoscape-tooltip', 'bbox'),
            Output('cytoscape-tooltip', 'children'),
            Input('one-line-diagram', 'mouseoverNodeData'),
            Input('one-line-diagram', 'mouseoverEdgeData'),
            prevent_initial_call=True
        )
        def update_tooltip(node_data, edge_data):
            if node_data is None and edge_data is None:
                return False, no_update, no_update
            
            if node_data is not None:
                data = node_data
            else:
                data = edge_data
            
            # Return a valid bbox format for the tooltip
            bbox = {
                'x0': 100,
                'y0': 100,
                'x1': 200,
                'y1': 200
            }
            
            tooltip_content = self._get_tooltip({'data': data})
            
            return True, bbox, tooltip_content
        
        @app.callback(
            Output('node-info', 'children'),
            Input('one-line-diagram', 'selectedNodeData'),
            prevent_initial_call=True
        )
        def show_node_info(node_data):
            if not node_data:
                return None
            
            data = node_data[0]
            element_type = data.get('type', '').capitalize()
            
            info_components = [
                html.H4(f"{element_type} Details"),
                html.Hr(),
                *[html.Div([
                    html.Dt(key),
                    html.Dd(str(value)),
                ]) for key, value in data.items() if key not in ['id', 'label', 'parent', 'type']]
            ]
            
            return info_components
        
        @app.callback(
            Output('one-line-diagram', 'stylesheet'),
            Input('label-visibility', 'value'),
            Input('node-size-slider', 'value'),
            prevent_initial_call=True
        )
        def update_styles(label_visibility, node_size):
            # Update node size in styles
            stylesheet = self._get_default_stylesheet()
            
            # Update label visibility based on selection
            for style in stylesheet:
                if style['selector'] == 'node':
                    if label_visibility == 'none':
                        style['style']['content'] = ''
                    elif label_visibility == 'buses':
                        style['style']['content'] = 'data(label)'
                        # Add a custom class for non-bus nodes to hide their labels
                        stylesheet.append({
                            'selector': 'node[type != "bus"]',
                            'style': {
                                'content': ''
                            }
                        })
                    else:  # 'all'
                        style['style']['content'] = 'data(label)'
            
            # Update node sizes
            for style in stylesheet:
                if 'node' in style['selector'] and 'style' in style:
                    if 'width' in style['style'] and 'height' in style['style']:
                        # Scale the size based on the slider value
                        base_size = NODE_STYLES.get(style['selector'].replace('node[type = "', '').replace('"]', ''), {})
                        if base_size:
                            scale = node_size / 40  # 40 is the default size
                            style['style']['width'] = f"{base_size['width'] * scale}px"
                            style['style']['height'] = f"{base_size['height'] * scale}px"
            
            return stylesheet
        
        @app.callback(
            Output('one-line-diagram', 'elements'),
            Input('reset-layout', 'n_clicks'),
            prevent_initial_call=True
        )
        def reset_layout(n_clicks):
            if n_clicks is None:
                return no_update
            
            # Clear saved positions
            self.node_positions = {}
            
            # Regenerate elements with default positions
            elements = self._get_node_elements() + self._get_edge_elements()
            elements.extend(self._get_compound_elements())
            
            return elements
        
        @app.callback(
            Output('save-layout', 'children'),
            Input('save-layout', 'n_clicks'),
            State('one-line-diagram', 'elements'),
            prevent_initial_call=True
        )
        def save_layout(n_clicks, elements):
            if n_clicks is None:
                return no_update
            
            # Extract node positions from elements
            for element in elements:
                if 'position' in element and 'data' in element and 'id' in element['data']:
                    self.node_positions[element['data']['id']] = element['position']
            
            # Save to file
            self._save_layout()
            
            return "Layout Saved!"

def create_one_line_diagram(model: Any, debug: bool = False) -> dash.Dash:
    """
    Create and run a Dash application for the one-line diagram.
    
    Args:
        model: The PSSE model to visualize
        debug: Whether to run in debug mode
        
    Returns:
        dash.Dash: The Dash application instance
    """
    # Initialize the Dash app
    app = dash.Dash(__name__)
    
    # Create the one-line diagram
    diagram = OneLineDiagram(model)
    
    # Set the app layout
    app.layout = diagram.get_app_layout()
    
    # Register callbacks
    diagram.register_callbacks(app)
    
    # Add custom CSS
    app.index_string = '''
    <!DOCTYPE html>
    <html>
        <head>
            <title>One-Line Diagram</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body {
                    font-family: Arial, sans-serif;
                }
                .cytoscape-container {
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }
                .btn {
                    margin-right: 5px;
                }
                .slider-container {
                    padding: 20px;
                }
                .node-info {
                    position: absolute;
                    right: 20px;
                    top: 100px;
                    width: 300px;
                    z-index: 1000;
                    background: white;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    padding: 15px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }
                .node-info h4 {
                    margin-top: 0;
                    color: #333;
                }
                .node-info dt {
                    font-weight: bold;
                    margin-top: 10px;
                }
                .node-info dd {
                    margin-left: 0;
                    margin-bottom: 5px;
                }
            </style>
        </head>
        <body>
            {%app_entry%}
            <footer>
                {%config%}
                {%scripts%}
                {%renderer%}
            </footer>
        </body>
    </html>
    '''
    
    return app

# Example usage
if __name__ == '__main__':
    # This is just for testing - in practice, you would pass a real PSSE model
    class MockModel:
        def __init__(self):
            self.name = "Test Model"
            self.network = type('Network', (), {
                'bus': pd.DataFrame({
                    'i': [1, 2, 3],
                    'baskv': [230, 230, 500],
                    'area': [1, 1, 2],
                    'zone': [1, 1, 1],
                    'name': ['Bus 1', 'Bus 2', 'Bus 3']
                }),
                'generator': pd.DataFrame({
                    'i': [1, 2],
                    'id': ['G1', 'G2'],
                    'pg': [100, 200],
                    'qg': [20, 30],
                    'pt': [100, 200],
                    'pb': [0, 0]
                }),
                'load': pd.DataFrame({
                    'i': [2, 3],
                    'id': ['L1', 'L2'],
                    'pl': [50, 150],
                    'ql': [10, 25]
                }),
                'acline': pd.DataFrame({
                    'i': [1, 2],
                    'j': [2, 3],
                    'ckt': ['1', '1'],
                    'r': [0.01, 0.02],
                    'x': [0.1, 0.15],
                    'b': [0.0, 0.0],
                    'ratea': [200, 200],
                    'rateb': [250, 250],
                    'ratec': [300, 300]
                })
            })
    
    # Create and run the app
    app = create_one_line_diagram(MockModel(), debug=True)
    app.run_server(debug=True)
