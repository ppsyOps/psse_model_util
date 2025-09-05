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
        'shape': 'rectangle',  # Buses as horizontal bars
        'background-color': '#2B7CE9',  # Blue
        'width': 30,  # Wider than tall for horizontal bar
        'height': 10,
        'border-width': 2,
        'border-color': '#000000',
    },
    'generator': {
        'shape': 'ellipse',  # Generators as circles
        'background-color': '#FFA500',  # Orange
        'width': 20,
        'height': 20,
        'border-width': 2,
        'border-color': '#000000',
    },
    'load': {
        'shape': 'triangle',  # Loads as triangles
        'background-color': '#28A745',  # Green
        'width': 20,
        'height': 20,
        'border-width': 2,
        'border-color': '#000000',
        'shape-polygon-points': '-0.5 -0.8, 0.5 -0.8, 0 0.8'  # Pointing up
    },
    'transformer': {
        'shape': 'diamond',
        'background-color': '#6F42C1',  # Purple
        'width': 20,
        'height': 20,
        'border-width': 2,
        'border-color': '#000000',
    },
    'shunt': {
        'shape': 'octagon',
        'background-color': '#DC3545',  # Red
        'width': 20,
        'height': 20,
        'border-width': 2,
        'border-color': '#000000',
    },
    'default': {
        'shape': 'ellipse',
        'background-color': '#6C757D',  # Gray
        'width': 15,
        'height': 15,
        'border-width': 2,
        'border-color': '#000000',
    }
}

# Default edge style for bus-to-bus connections
EDGE_STYLE = {
    'width': 1,  # Thin line
    'line-color': '#000000',  # Black
    'target-arrow-shape': 'none',
    'curve-style': 'bezier',
    'line-style': 'solid',
}

# Equipment connection style (for bus-to-equipment connections)
EQUIPMENT_CONNECTION_STYLE = {
    'width': 1,  # Thin line
    'line-color': '#000000',  # Black
    'line-style': 'dashed',
    'curve-style': 'straight',
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
    node_size: int = 20
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
                    'font-size': '9px',
                    'font-weight': 'bold',
                    'text-outline-width': '2px',
                    'text-outline-color': '#000',
                    'overlay-opacity': 0,
                    'text-wrap': 'wrap',
                    'text-max-width': '100px',
                    'text-margin-y': '0px',
                    'text-margin-x': '0px',
                }
            },
            # Default edge style (applies to all edges unless overridden)
            {
                'selector': 'edge',
                'style': {
                    'width': '1',  # Force thin lines
                    'line-color': '#000000',  # Force black color
                    'target-arrow-shape': 'none',
                    'curve-style': 'bezier',
                    'line-style': 'solid',
                    'z-index': 2,  # Draw bus connections on top
                }
            },
            # Equipment connection styles
            {
                'selector': '.equipment-connection',
                'style': {
                    'width': '1',  # Thin lines
                    'line-color': '#000000',  # Black color
                    'line-style': 'dashed',
                    'curve-style': 'straight',
                    'z-index': 1,  # Draw behind bus connections
                    'line-cap': 'round',
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
        """Convert model buses and equipment to node elements with proper spacing."""
        elements = []
        bus_equipment = {}  # Track equipment for each bus
        
        # First pass: add all buses in a grid
        for idx, (_, bus) in enumerate(self.model.network.bus.iterrows()):
            bus_id = f"bus_{bus['i']}"
            bus_equipment[bus_id] = []
            
            # Calculate grid position with more spacing
            row = idx // 2  # Two columns
            col = idx % 2   
            
            # Get saved position or calculate new one
            if bus_id in self.node_positions:
                position = self.node_positions[bus_id]
            else:
                position = {
                    'x': 200 + col * 600,  # Increased horizontal spacing
                    'y': 100 + row * 400    # Increased vertical spacing
                }
            
            # Add the bus
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
        
        # Second pass: add equipment with proper offsets
        equipment_spacing = 120  # pixels between equipment items
        
        # Add generators with offset from their bus
        if hasattr(self.model.network, 'generator'):
            for idx, (_, gen) in enumerate(self.model.network.generator.iterrows()):
                gen_id = f"gen_{gen['i']}_{gen['id']}"
                bus_id = f"bus_{gen['i']}"
                
                # Get bus position
                bus_pos = next((e['position'] for e in elements if e['data']['id'] == bus_id), {'x': 0, 'y': 0})
                
                # Calculate position below the bus with horizontal offset
                # Alternate sides for better spacing
                side_offset = 100 if idx % 2 == 0 else -100
                
                position = self.node_positions.get(gen_id, {
                    'x': bus_pos.get('x', 0) + side_offset,  # Alternate sides
                    'y': bus_pos.get('y', 0) + 50  # Closer to bus (reduced from 80)
                })
                
                elements.append({
                    'data': {
                        'id': gen_id,
                        'label': f"Gen {gen['i']}:{gen['id']}",
                        'type': 'generator',
                        'pg': gen.get('pg', 0),
                        'qg': gen.get('qg', 0),
                        'pt': gen.get('pt', 0),
                        'pb': gen.get('pb', 0),
                    },
                    'position': position,
                    'classes': 'generator-node',
                    'grabbable': True,
                    'selectable': True,
                })
        
        # Add loads with offset from their bus
        if hasattr(self.model.network, 'load'):
            for idx, (_, load) in enumerate(self.model.network.load.iterrows()):
                load_id = f"load_{load['i']}_{load['id']}"
                bus_id = f"bus_{load['i']}"
                
                # Get bus position
                bus_pos = next((e['position'] for e in elements if e['data']['id'] == bus_id), {'x': 0, 'y': 0})
                
                # Calculate position below the bus with horizontal offset
                # Opposite side from generators for balance
                side_offset = -100 if idx % 2 == 0 else 100
                
                position = self.node_positions.get(load_id, {
                    'x': bus_pos.get('x', 0) + side_offset,  # Opposite side from generator
                    'y': bus_pos.get('y', 0) + 80  # Below the bus
                })
                
                elements.append({
                    'data': {
                        'id': load_id,
                        'label': f"Load {load['i']}:{load['id']}",
                        'type': 'load',
                        'pl': load.get('pl', 0),
                        'ql': load.get('ql', 0),
                    },
                    'position': position,
                    'classes': 'load-node',
                    'grabbable': True,
                    'selectable': True,
                })
                
        return elements
        
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
        """Convert model branches to edge elements and create connections to equipment."""
        elements = []
        
        # Add connections between buses and their equipment first (so they're drawn underneath)
        
        # Connect generators to their buses
        if hasattr(self.model.network, 'generator'):
            for _, gen in self.model.network.generator.iterrows():
                gen_id = f"gen_{gen['i']}_{gen['id']}"
                bus_id = f"bus_{gen['i']}"
                edge_id = f"gen_conn_{gen['i']}_{gen['id']}"
                
                elements.append({
                    'data': {
                        'id': edge_id,
                        'source': bus_id,
                        'target': gen_id,
                        'type': 'connection',
                        'line-style': 'dashed',
                    },
                    'classes': 'equipment-connection',
                    'selectable': False,
                })
        
        # Connect loads to their buses
        if hasattr(self.model.network, 'load'):
            for _, load in self.model.network.load.iterrows():
                load_id = f"load_{load['i']}_{load['id']}"
                bus_id = f"bus_{load['i']}"
                edge_id = f"load_conn_{load['i']}_{load['id']}"
                
                elements.append({
                    'data': {
                        'id': edge_id,
                        'source': bus_id,
                        'target': load_id,
                        'type': 'connection',
                        'line-style': 'dashed',
                    },
                    'classes': 'equipment-connection',
                    'selectable': False,
                })
        
        # Add AC lines between buses
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
        
        # Create the Cytoscape component with improved layout
        return cyto.Cytoscape(
            id='one-line-diagram',
            elements=self.elements,
            layout={
                'name': 'cose',  # Use CoSE (Compound Spring Embedder) layout
                'animate': True,
                'nodeDimensionsIncludeLabels': True,
                'idealEdgeLength': 200,  # Increased ideal edge length
                'nodeRepulsion': 10000,  # Increased repulsion to spread nodes
                'edgeElasticity': 0.3,   # Slightly less elastic edges
                'nestingFactor': 0.1,
                'gravity': 0.2,          # Reduced gravity to prevent clustering
                'numIter': 5000,         # More iterations for better layout
                'initialTemp': 1000,     # Higher initial temperature for better initial spread
                'coolingFactor': 0.95,   # Slower cooling
                'minTemp': 1.0,
                'randomize': True,
                'componentSpacing': 100,  # Space between components
                'nodeOverlap': 20,       # Prevent node overlap
                'refresh': 20,           # Refresh rate
                'fit': True,             # Fit to viewport
                'padding': 30            # Padding around the layout
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
            Input('one-line-diagram', 'tapNode'),
            Input('one-line-diagram', 'tapEdge'),
            prevent_initial_call=True
        )
        def update_tooltip(node_data, edge_data, tap_node, tap_edge):
            if node_data is None and edge_data is None:
                return False, no_update, no_update
            
            # Default position for the tooltip
            x_pos = 100
            y_pos = 100
            
            # If we have node data, position the tooltip relative to the node
            if node_data is not None:
                data = node_data
                # Use the node's position if available, otherwise use default
                if 'position' in data and data['position'] is not None:
                    x_pos = data['position'].get('x', 100) + 20
                    y_pos = data['position'].get('y', 100) - 50
            else:
                data = edge_data
                # For edges, use a fixed position for now
                x_pos = 150
                y_pos = 150
            
            # Define the tooltip bounding box
            bbox = {
                'x0': x_pos,
                'y0': y_pos,
                'x1': x_pos + 200,  # Fixed width
                'y1': y_pos + 100   # Fixed height
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
