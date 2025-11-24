"""
FireBridge Plasma CAM - Professional Edition
Complete plasma cutting toolpath generator with corner-based lead positioning
Author: Built for Redvernon1
Date: 2025-01-21
Updated: 2025-11-22 - Corner-based lead-in/out positioning
"""

import sys
import math
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET
import re
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QFileDialog, 
                             QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox,
                             QCheckBox, QGroupBox, QTabWidget, QMessageBox, 
                             QSplitter, QTableWidget, QTableWidgetItem, QHeaderView,
                             QMenu, QScrollArea, QInputDialog)
from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QPainterPath, QFont, QRadialGradient, QAction

# Post-processor templates with all major controllers
POST_PROCESSORS = {
    'fluidnc': {
        'name': 'FluidNC / grblHAL',
        'ext': '.nc',
        'header': '''G21 (Metric)
G90 (Absolute)
G17 (XY Plane)
$H (Home)
G92.1 (Clear offsets)
G0 Z{safe_z}
M3 S{power}
{coolant_start}''',
        'touch_off': '''G38.2 Z-{probe_depth} F{probe_feed} (Probe)
G92 Z0 (Zero Z)
G0 Z{retract} (Retract)
''',
        'pierce': '''G0 Z{pierce_height}
M3 S{power}
G4 P{pierce_delay}
G1 Z{cut_height} F500
''',
        'cut': 'G1 X{x:.3f} Y{y:.3f} F{feed}',
        'arc_cw': 'G2 X{x:.3f} Y{y:.3f} I{i:.3f} J{j:.3f} F{feed}',
        'arc_ccw': 'G3 X{x:.3f} Y{y:.3f} I{i:.3f} J{j:.3f} F{feed}',
        'end': 'M5\nG0 Z{safe_z}',
        'footer': 'G0 X0 Y0\nM2'
    },
    'mach3': {
        'name': 'Mach3 / Mach4',
        'ext': '.tap',
        'header': '''G20 (Inches - change to G21 for metric)
G90 G17 G40 G49 G80
G0 Z{safe_z}
''',
        'touch_off': '''G31 Z-{probe_depth} F{probe_feed}
G92 Z0
G0 Z{retract}
''',
        'pierce': '''G0 Z{pierce_height}
M3
G4 P{pierce_delay}
G1 Z{cut_height} F20
''',
        'cut': 'G1 X{x:.4f} Y{y:.4f} F{feed}',
        'arc_cw': 'G2 X{x:.4f} Y{y:.4f} I{i:.4f} J{j:.4f} F{feed}',
        'arc_ccw': 'G3 X{x:.4f} Y{y:.4f} I{i:.4f} J{j:.4f} F{feed}',
        'end': 'M5\nG0 Z{safe_z}',
        'footer': 'G0 X0 Y0\nM30'
    },
    'linuxcnc': {
        'name': 'LinuxCNC (with PlasmaC)',
        'ext': '.ngc',
        'header': '''G21 G90 G17 G40 G49 G80
G54
F#<_hal[plasmac.cut-feed-rate]>
G0 Z{safe_z}
''',
        'touch_off': '''G38.2 Z-{probe_depth} F{probe_feed}
G92 Z0
G0 Z{retract}
''',
        'pierce': '''M62 P1 (THC off)
G0 Z{pierce_height}
M3 $0
G4 P{pierce_delay}
M63 P1 (THC on)
G1 Z{cut_height} F500
''',
        'cut': 'G1 X{x:.3f} Y{y:.3f} F{feed}',
        'arc_cw': 'G2 X{x:.3f} Y{y:.3f} I{i:.3f} J{j:.3f} F{feed}',
        'arc_ccw': 'G3 X{x:.3f} Y{y:.3f} I{i:.3f} J{j:.3f} F{feed}',
        'thc_off': 'M62 P1',
        'thc_on': 'M63 P1',
        'end': 'M5 M65 P1\nG0 Z{safe_z}',
        'footer': 'G0 X0 Y0\nM2'
    },
    'uccnc': {
        'name': 'UCCNC',
        'ext': '.tap',
        'header': '''G21 G90 G17
G0 Z{safe_z}
M3 S{power}
''',
        'touch_off': '''G31 Z-{probe_depth} F{probe_feed}
G92 Z0
G0 Z{retract}
''',
        'pierce': '''G0 Z{pierce_height}
M3
G4 P{pierce_delay}
G1 Z{cut_height} F500
''',
        'cut': 'G1 X{x:.3f} Y{y:.3f} F{feed}',
        'arc_cw': 'G2 X{x:.3f} Y{y:.3f} I{i:.3f} J{j:.3f} F{feed}',
        'arc_ccw': 'G3 X{x:.3f} Y{y:.3f} I{i:.3f} J{j:.3f} F{feed}',
        'end': 'M5\nG0 Z{safe_z}',
        'footer': 'G0 X0 Y0\nM30'
    },
    'hypertherm': {
        'name': 'Hypertherm Edge/Phoenix',
        'ext': '.nc',
        'header': 'W1,1\n',
        'pierce': 'W2,1,{pierce_delay}\nW3,0,{pierce_height},{pierce_delay}\n',
        'cut': 'W4,{x:.3f},{y:.3f},{cut_height},{feed}\n',
        'end': 'W5\n',
        'footer': 'W6\n'
    }
}

# Material presets
MATERIAL_PRESETS = {
    'Mild Steel 16ga': {
        'pierce_height': 3.8,
        'cut_height': 1.5,
        'pierce_delay': 0.8,
        'feed': 4500,
        'kerf': 1.2
    },
    'Mild Steel 14ga': {
        'pierce_height': 3.8,
        'cut_height': 1.5,
        'pierce_delay': 1.0,
        'feed': 4000,
        'kerf': 1.3
    },
    'Mild Steel 11ga': {
        'pierce_height': 4.0,
        'cut_height': 1.8,
        'pierce_delay': 1.2,
        'feed': 3500,
        'kerf': 1.4
    },
    'Mild Steel 1/8"': {
        'pierce_height': 4.2,
        'cut_height': 2.0,
        'pierce_delay': 1.5,
        'feed': 3000,
        'kerf': 1.5
    },
    'Stainless 16ga': {
        'pierce_height': 4.0,
        'cut_height': 1.8,
        'pierce_delay': 1.0,
        'feed': 3800,
        'kerf': 1.3
    },
    'Aluminum 1/8"': {
        'pierce_height': 4.5,
        'cut_height': 2.2,
        'pierce_delay': 1.2,
        'feed': 5000,
        'kerf': 1.6
    }
}

class InteractivePreviewCanvas(QWidget):
    """Enhanced interactive canvas with zoom, pan, and selection"""
    
    path_selected = pyqtSignal(int)
    kerf_changed = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.lbl_stats = QLabel("")  # ensure exists before UI builds
        self.paths = []
        self.selected_path_idx = None
        self.scale = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.show_leads = True
        self.show_rapids = True
        self.setMinimumSize(400, 400)
        self.setStyleSheet("background-color: #1a1a1a;")
        
        # Animation properties
        self.animate = False
        self.animation_progress = 0.0
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.update_animation)
        self.animation_timer.setInterval(50)
        self.show_full_paths = False
        
        # Interactive features
        self.panning = False
        self.pan_start = QPointF()
        self.pan_offset_start = (0, 0)
        self.hover_path_idx = None
        self.show_dimensions = True
        self.show_grid = True
        self.grid_size = 10  # mm
        
        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.WheelFocus)
        
        # Cursor
        self.setCursor(Qt.CursorShape.CrossCursor)
    
    def wheelEvent(self, event):
        """Mouse wheel zoom with smooth scaling"""
        # Get mouse position in widget coordinates
        mouse_x = event.position().x()
        mouse_y = event.position().y()
        
        # Convert mouse position to world coordinates before zoom
        world_x = (mouse_x / self.scale) - self.offset_x
        world_y = ((self.height() - mouse_y) / self.scale) - self.offset_y
        
        # Calculate zoom factor (smooth zooming)
        degrees = event.angleDelta().y() / 8
        steps = degrees / 15
        zoom_factor = 1.15 ** steps  # 15% zoom per step
        
        # Apply zoom with limits
        new_scale = self.scale * zoom_factor
        new_scale = max(0.1, min(50.0, new_scale))  # Limit between 0.1x and 50x
        
        if new_scale != self.scale:
            self.scale = new_scale
            
            # Adjust offsets to keep mouse position fixed in world space
            self.offset_x = (mouse_x / self.scale) - world_x
            self.offset_y = ((self.height() - mouse_y) / self.scale) - world_y
            
            self.update()
            event.accept()
    
    def mousePressEvent(self, event):
        """Handle mouse press for selection and pan start"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if we clicked on a path
            click_x = event.pos().x()
            click_y = event.pos().y()
            
            clicked_on_path = False
            for idx, path in enumerate(self.paths):
                if self.is_click_on_path(click_x, click_y, path):
                    self.selected_path_idx = idx
                    self.path_selected.emit(idx)
                    clicked_on_path = True
                    self.update()
                    break
            
            if not clicked_on_path:
                # Start panning if we didn't click on a path
                self.panning = True
                self.pan_start = event.position()
                self.pan_offset_start = (self.offset_x, self.offset_y)
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
        
        elif event.button() == Qt.MouseButton.MiddleButton:
            # Middle button - start pan regardless of path
            self.panning = True
            self.pan_start = event.position()
            self.pan_offset_start = (self.offset_x, self.offset_y)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for panning and hover effects"""
        if self.panning:
            # Pan the view
            dx = (event.position().x() - self.pan_start.x()) / self.scale
            dy = -(event.position().y() - self.pan_start.y()) / self.scale
            
            self.offset_x = self.pan_offset_start[0] + dx
            self.offset_y = self.pan_offset_start[1] + dy
            self.update()
        else:
            # Check for hover over paths
            mouse_x = event.pos().x()
            mouse_y = event.pos().y()
            
            old_hover = self.hover_path_idx
            self.hover_path_idx = None
            
            for idx, path in enumerate(self.paths):
                if self.is_click_on_path(mouse_x, mouse_y, path):
                    self.hover_path_idx = idx
                    self.setCursor(Qt.CursorShape.PointingHandCursor)
                    break
            
            if self.hover_path_idx is None:
                self.setCursor(Qt.CursorShape.CrossCursor)
            
            if old_hover != self.hover_path_idx:
                self.update()
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release"""
        if self.panning:
            self.panning = False
            self.setCursor(Qt.CursorShape.CrossCursor)
    
    def mouseDoubleClickEvent(self, event):
        """Double click to fit view or zoom to path"""
        if self.selected_path_idx is not None:
            # Zoom to selected path
            self.zoom_to_path(self.selected_path_idx)
        else:
            # Fit all to view
            self.fit_to_view()
    
    def zoom_to_path(self, path_idx):
        """Zoom to show a specific path"""
        if path_idx >= len(self.paths):
            return
        
        path = self.paths[path_idx]
        points = path.get('points', [])
        
        if not points:
            return
        
        # Find bounding box of this path
        min_x = min(p[0] for p in points)
        max_x = max(p[0] for p in points)
        min_y = min(p[1] for p in points)
        max_y = max(p[1] for p in points)
        
        width = max_x - min_x
        height = max_y - min_y
        
        # Add some padding
        padding = max(width, height) * 0.2
        width += 2 * padding
        height += 2 * padding
        
        # Calculate scale to fit
        scale_x = self.width() / width if width > 0 else 1
        scale_y = self.height() / height if height > 0 else 1
        self.scale = min(scale_x, scale_y) * 0.8  # 80% to leave margin
        
        # Center the path
        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        
        self.offset_x = self.width() / (2 * self.scale) - center_x
        self.offset_y = self.height() / (2 * self.scale) - center_y
        
        self.update()
    
    def keyPressEvent(self, event):
        """Keyboard shortcuts"""
        if event.key() == Qt.Key.Key_F:
            self.fit_to_view()
        elif event.key() == Qt.Key.Key_G:
            self.show_grid = not self.show_grid
            self.update()
        elif event.key() == Qt.Key.Key_D:
            self.show_dimensions = not self.show_dimensions
            self.update()
        elif event.key() == Qt.Key.Key_Plus or event.key() == Qt.Key.Key_Equal:
            self.scale *= 1.2
            self.update()
        elif event.key() == Qt.Key.Key_Minus:
            self.scale /= 1.2
            self.update()
        elif event.key() == Qt.Key.Key_Space:
            if self.animate:
                self.stop_animation()
            else:
                self.start_animation()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Background
        painter.fillRect(self.rect(), QColor(20, 20, 20))
        
        # Draw grid if enabled
        if self.show_grid:
            self.draw_grid(painter)
        
        # Draw ruler/scale reference
        self.draw_scale_reference(painter)
        
        if not self.paths:
            # Draw help text when no paths loaded
            painter.setPen(QPen(QColor(100, 100, 100), 1))
            painter.setFont(QFont('Arial', 12))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 
                           "Load a file to preview\n\nControls:\n"
                           "🖱 Wheel: Zoom\n"
                           "🖱 Left Drag: Pan\n"
                           "🖱 Double-click: Fit/Zoom to path\n"
                           "⌨ F: Fit all\n"
                           "⌨ G: Toggle grid\n"
                           "⌨ D: Toggle dimensions")
            return
        
        # Draw paths
        for path_idx, path in enumerate(self.paths):
            self.draw_path(painter, path, path_idx)
        
        # Draw dimensions if enabled
        if self.show_dimensions and self.selected_path_idx is not None:
            self.draw_path_dimensions(painter, self.paths[self.selected_path_idx])
        
        # Info overlay
        self.draw_info_overlay(painter)
    
    def draw_grid(self, painter):
        """Draw measurement grid"""
        painter.setPen(QPen(QColor(40, 40, 40), 1))
        
        # Calculate grid spacing in screen coordinates
        grid_screen = self.grid_size * self.scale
        
        # Adjust grid size if too dense or sparse
        while grid_screen < 20:
            self.grid_size *= 2
            grid_screen = self.grid_size * self.scale
        while grid_screen > 100:
            self.grid_size /= 2
            grid_screen = self.grid_size * self.scale
        
        # Calculate visible range in world coordinates
        left = -self.offset_x
        right = (self.width() / self.scale) - self.offset_x
        bottom = -self.offset_y
        top = (self.height() / self.scale) - self.offset_y
        
        # Draw vertical lines
        x = (int(left / self.grid_size) - 1) * self.grid_size
        while x <= right + self.grid_size:
            screen_x = (x + self.offset_x) * self.scale
            painter.drawLine(int(screen_x), 0, int(screen_x), self.height())
            x += self.grid_size
        
        # Draw horizontal lines
        y = (int(bottom / self.grid_size) - 1) * self.grid_size
        while y <= top + self.grid_size:
            screen_y = self.height() - (y + self.offset_y) * self.scale
            painter.drawLine(0, int(screen_y), self.width(), int(screen_y))
            y += self.grid_size
    
    def draw_scale_reference(self, painter):
        """Draw a scale reference in corner"""
        painter.setPen(QPen(QColor(150, 150, 150), 2))
        painter.setFont(QFont('Monospace', 10))
        
        # Draw 50mm reference line
        ref_length = 50  # mm
        ref_pixels = ref_length * self.scale
        
        if ref_pixels > 30 and ref_pixels < 300:  # Only show if reasonable size
            x_start = self.width() - 120
            y_pos = self.height() - 30
            
            painter.drawLine(int(x_start), int(y_pos), 
                           int(x_start + ref_pixels), int(y_pos))
            painter.drawLine(int(x_start), int(y_pos - 5), 
                           int(x_start), int(y_pos + 5))
            painter.drawLine(int(x_start + ref_pixels), int(y_pos - 5), 
                           int(x_start + ref_pixels), int(y_pos + 5))
            
            painter.drawText(int(x_start + ref_pixels/2 - 20), int(y_pos - 10), 
                           f"{ref_length}mm")
    
    def draw_path(self, painter, path, path_idx):
        """Draw a single path with enhanced visuals"""
        points = path.get('points', [])
        if len(points) < 2:
            return
        
        is_selected = (path_idx == self.selected_path_idx)
        is_hover = (path_idx == self.hover_path_idx)
        
        # Transform points to screen coordinates
        transformed = []
        for pt in points:
            x = (pt[0] + self.offset_x) * self.scale
            y = self.height() - (pt[1] + self.offset_y) * self.scale
            transformed.append(QPointF(x, y))
        
        # Get path color
        color = self.get_path_color(path, is_selected)
        
        # Draw path with effects
        if is_hover and not is_selected:
            # Hover glow effect
            painter.setPen(QPen(color.lighter(150), 4, Qt.PenStyle.SolidLine))
            for i in range(len(transformed) - 1):
                painter.drawLine(transformed[i], transformed[i + 1])
        
        if is_selected:
            # Selected glow
            painter.setPen(QPen(color.lighter(180), 6, Qt.PenStyle.SolidLine))
            for i in range(len(transformed) - 1):
                painter.drawLine(transformed[i], transformed[i + 1])
        
        # Main path
        width = 3 if is_selected else 2
        painter.setPen(QPen(color, width))
        for i in range(len(transformed) - 1):
            painter.drawLine(transformed[i], transformed[i + 1])
        
        # Draw start point marker
        if is_selected or is_hover:
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            painter.setPen(QPen(color, 2))
            painter.drawEllipse(transformed[0], 8, 8)
            
            # Draw arrow showing cut direction
            if len(transformed) > 1:
                painter.setPen(QPen(color, 2))
                self.draw_arrow(painter, transformed[0], transformed[1])
    
    def draw_arrow(self, painter, start, end):
        """Draw directional arrow"""
        # Calculate arrow position (25% along the line)
        t = 0.25
        mid_x = start.x() + t * (end.x() - start.x())
        mid_y = start.y() + t * (end.y() - start.y())
        
        # Calculate arrow direction
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.sqrt(dx*dx + dy*dy)
        
        if length < 1:
            return
        
        dx /= length
        dy /= length
        
        # Arrow size
        arrow_len = 10
        arrow_width = 4
        
        # Arrow points
        tip_x = mid_x + dx * arrow_len
        tip_y = mid_y + dy * arrow_len
        base1_x = mid_x - dy * arrow_width
        base1_y = mid_y + dx * arrow_width
        base2_x = mid_x + dy * arrow_width
        base2_y = mid_y - dx * arrow_width
        
        # Draw arrow
        painter.drawLine(QPointF(base1_x, base1_y), QPointF(tip_x, tip_y))
        painter.drawLine(QPointF(base2_x, base2_y), QPointF(tip_x, tip_y))
    
    def draw_path_dimensions(self, painter, path):
        """Draw dimensions for selected path"""
        points = path.get('points', [])
        if not points:
            return
        
        # Calculate bounding box
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        width = max_x - min_x
        height = max_y - min_y
        
        # Transform to screen coordinates
        screen_min_x = (min_x + self.offset_x) * self.scale
        screen_max_x = (max_x + self.offset_x) * self.scale
        screen_min_y = self.height() - (max_y + self.offset_y) * self.scale
        screen_max_y = self.height() - (min_y + self.offset_y) * self.scale
        
        # Draw dimension lines
        painter.setPen(QPen(QColor(255, 255, 100), 1, Qt.PenStyle.DashLine))
        painter.setFont(QFont('Monospace', 10))
        
        # Width dimension
        offset = 20
        painter.drawLine(int(screen_min_x), int(screen_min_y - offset),
                        int(screen_max_x), int(screen_min_y - offset))
        painter.drawText(int((screen_min_x + screen_max_x)/2 - 30), 
                        int(screen_min_y - offset - 5),
                        f"{width:.1f}mm")
        
        # Height dimension
        painter.drawLine(int(screen_max_x + offset), int(screen_min_y),
                        int(screen_max_x + offset), int(screen_max_y))
        painter.save()
        painter.translate(int(screen_max_x + offset + 15), 
                         int((screen_min_y + screen_max_y)/2))
        painter.rotate(-90)
        painter.drawText(-30, 0, f"{height:.1f}mm")
        painter.restore()
    
    def draw_info_overlay(self, painter):
        """Draw info overlay with current status"""
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        painter.setFont(QFont('Monospace', 10))
        
        # Top left info
        y_pos = 20
        
        # Zoom level
        zoom_percent = self.scale * 100
        painter.drawText(10, y_pos, f"Zoom: {zoom_percent:.0f}%")
        y_pos += 20
        
        # Grid size
        if self.show_grid:
            painter.drawText(10, y_pos, f"Grid: {self.grid_size:.0f}mm")
            y_pos += 20
        
        # Path counts
        if self.paths:
            outside = sum(1 for p in self.paths if p.get('kerf_type', '') == 'outside')
            inside = sum(1 for p in self.paths if p.get('kerf_type', '') == 'inside')
            none = sum(1 for p in self.paths if p.get('kerf_type', '') == 'none')
            
            painter.drawText(10, y_pos, 
                f"Paths: {len(self.paths)} | Out: {outside} | In: {inside} | None: {none}")
        
        # Bottom help text
        help_text = "Mouse: Wheel=Zoom, Drag=Pan, Click=Select | Keys: F=Fit, G=Grid, D=Dims"
        painter.drawText(10, self.height() - 10, help_text)
    
    def set_paths(self, paths):
        """Set paths for display"""
        self.paths = paths
        self.show_full_paths = True
        self.animate = False
        self.animation_progress = 0.0
        self.fit_to_view()
        self.update()
    
    def get_path_color(self, path, is_selected=False):
        """Get color based on kerf type"""
        if is_selected:
            return QColor(255, 255, 0)  # Yellow for selected
        
        kerf_type = path.get('kerf_type', 'outside')
        
        if kerf_type == 'outside':
            return QColor(255, 77, 109)  # Red
        elif kerf_type == 'inside':
            return QColor(52, 152, 219)  # Blue
        else:  # 'none'
            return QColor(52, 211, 153)  # Green
    
    def mousePressEvent(self, event):
        """Handle mouse click to select path"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Find which path was clicked
            click_x = event.pos().x()
            click_y = event.pos().y()
            
            for idx, path in enumerate(self.paths):
                if self.is_click_on_path(click_x, click_y, path):
                    self.selected_path_idx = idx
                    self.path_selected.emit(idx)
                    self.update()
                    return
            
            # Click on empty space - deselect
            self.selected_path_idx = None
            self.update()
    
    def contextMenuEvent(self, event):
        """Handle right-click context menu for per-path kerf, leads, feed, and scale."""
        # Try to select the path that was right-clicked on
        click_pos = event.pos()
        click_x = click_pos.x()
        click_y = click_pos.y()
        
        clicked_idx = None
        for idx, path in enumerate(self.paths):
            if self.is_click_on_path(click_x, click_y, path):
                clicked_idx = idx
                break
        
        if clicked_idx is not None:
            self.selected_path_idx = clicked_idx
            self.path_selected.emit(clicked_idx)
        
        if self.selected_path_idx is None:
            event.ignore()
            return
        
        path = self.paths[self.selected_path_idx]
        
        menu = QMenu(self)
        
        # --- Kerf type submenu ---
        kerf_menu = menu.addMenu("Kerf Type")
        
        action_outside = QAction("🔴 Outside Kerf", self)
        action_outside.triggered.connect(lambda: self.set_path_kerf_type('outside'))
        kerf_menu.addAction(action_outside)
        
        action_inside = QAction("🔵 Inside Kerf", self)
        action_inside.triggered.connect(lambda: self.set_path_kerf_type('inside'))
        kerf_menu.addAction(action_inside)
        
        action_none = QAction("🟢 No Kerf", self)
        action_none.triggered.connect(lambda: self.set_path_kerf_type('none'))
        kerf_menu.addAction(action_none)
        
        # --- Lead enable / disable toggle ---
        leads_enabled = path.get('leads_enabled', True)
        action_toggle_leads = QAction(self)
        action_toggle_leads.setText("✅ Leads Enabled" if leads_enabled else "⛔ Leads Disabled")
        
        def toggle_leads():
            path['leads_enabled'] = not path.get('leads_enabled', True)
            self.kerf_changed.emit()
            self.update()
        
        action_toggle_leads.triggered.connect(toggle_leads)
        menu.addAction(action_toggle_leads)
        
        # --- Per-path feed override ---
        def set_feed_override():
            current_feed = path.get('feed', 0.0) or 0.0
            value, ok = QInputDialog.getDouble(
                self,
                "Feed Rate Override",
                "Feed rate for this path (mm/min, 0 = use global):",
                float(current_feed),
                0.0,
                100000.0,
                0,
            )
            if ok:
                if value <= 0:
                    path.pop('feed', None)
                else:
                    path['feed'] = value
                self.kerf_changed.emit()
                self.update()
        
        action_feed = QAction("Set Feed Rate…", self)
        action_feed.triggered.connect(set_feed_override)
        menu.addAction(action_feed)
        
        # --- Per-path scale / size ---
        def set_scale_override():
            current_scale = path.get('scale', 1.0)
            value, ok = QInputDialog.getDouble(
                self,
                "Scale / Size",
                "Scale this path (%):",
                float(current_scale * 100.0),
                1.0,
                1000.0,
                1,
            )
            if ok:
                path['scale'] = value / 100.0
                self.kerf_changed.emit()
                self.update()
        
        action_scale = QAction("Set Scale / Size…", self)
        action_scale.triggered.connect(set_scale_override)
        menu.addAction(action_scale)
        
        menu.exec(event.globalPos())
    

    def is_click_on_path(self, click_x, click_y, path):
        """Check if click is near any segment of the path"""
        points = path.get('points', [])
        if len(points) < 2:
            return False
        
        threshold = 10  # pixels
        
        for i in range(len(points) - 1):
            x1 = (points[i][0] + self.offset_x) * self.scale
            y1 = self.height() - (points[i][1] + self.offset_y) * self.scale
            x2 = (points[i+1][0] + self.offset_x) * self.scale
            y2 = self.height() - (points[i+1][1] + self.offset_y) * self.scale
            
            # Distance from point to line segment
            dist = self.point_to_segment_distance(click_x, click_y, x1, y1, x2, y2)
            if dist < threshold:
                return True
        
        return False
    
    def point_to_segment_distance(self, px, py, x1, y1, x2, y2):
        """Calculate distance from point to line segment"""
        dx = x2 - x1
        dy = y2 - y1
        
        if dx == 0 and dy == 0:
            return math.sqrt((px - x1)**2 + (py - y1)**2)
        
        t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
        
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy
        
        return math.sqrt((px - proj_x)**2 + (py - proj_y)**2)
    
    def set_path_kerf_type(self, kerf_type):
        """Set kerf type for selected path"""
        if self.selected_path_idx is not None and self.selected_path_idx < len(self.paths):
            self.paths[self.selected_path_idx]['kerf_type'] = kerf_type
            self.kerf_changed.emit()
            self.update()
    
    def start_animation(self):
        """Start the toolpath animation"""
        self.animate = True
        self.animation_progress = 0.0
        if not self.animation_timer.isActive():
            self.animation_timer.start()
        self.update()
    
    def stop_animation(self):
        """Stop the animation"""
        self.animate = False
        self.animation_progress = 1.0
        self.animation_timer.stop()
        self.update()
    
    def update_animation(self):
        """Update animation progress"""
        if self.animate:
            self.animation_progress += 0.01
            if self.animation_progress >= 1.0:
                self.stop_animation()
            else:
                self.update()
        else:
            self.animation_timer.stop()
    
    def fit_to_view(self):
        """Fit all paths to the canvas view"""
        if not self.paths:
            return
        
        min_x = min_y = float('inf')
        max_x = max_y = float('-inf')
        
        for path in self.paths:
            for pt in path.get('points', []):
                min_x = min(min_x, pt[0])
                max_x = max(max_x, pt[0])
                min_y = min(min_y, pt[1])
                max_y = max(max_y, pt[1])
        
        if min_x == float('inf'):
            return
        
        width = max_x - min_x
        height = max_y - min_y
        
        if width == 0 or height == 0:
            return
        
        padding = 40
        scale_x = (self.width() - 2*padding) / width
        scale_y = (self.height() - 2*padding) / height
        self.scale = min(scale_x, scale_y)
        
        self.offset_x = -min_x + (self.width() / self.scale - width) / 2
        self.offset_y = -min_y + (self.height() / self.scale - height) / 2
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Background
        painter.fillRect(self.rect(), QColor(20, 20, 20))
        
        # Grid
        painter.setPen(QPen(QColor(40, 40, 40), 1))
        grid_step = 50
        
        for x in range(0, self.width(), int(grid_step * self.scale) if self.scale > 0 else 50):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), int(grid_step * self.scale) if self.scale > 0 else 50):
            painter.drawLine(0, y, self.width(), y)
        
        if not self.paths:
            return
        
        total_paths = len(self.paths)
        current_path_idx = int(total_paths * self.animation_progress) if self.animate else total_paths
        
        # Draw each path
        for path_idx, path in enumerate(self.paths):
            points = path.get('points', [])
            if len(points) < 2:
                continue
            
            is_selected = (path_idx == self.selected_path_idx)
            has_kerf_set = 'kerf_type' in path and path['kerf_type'] in ['inside', 'outside', 'none']
            
            # Transform points to screen coordinates (apply per-path scale if set)
            transformed = []
            scale_factor = path.get('scale', 1.0)
            for pt in points:
                px = pt[0] * scale_factor
                py = pt[1] * scale_factor
                x = (px + self.offset_x) * self.scale
                y = self.height() - (py + self.offset_y) * self.scale
                transformed.append(QPointF(x, y))
            
            if len(transformed) < 2:
                continue
            
            # NOT animating - show all
            if not self.animate:
                # UNSELECTED PATHS - White dashed (won't be cut)
                if not has_kerf_set:
                    if is_selected:
                        painter.setPen(QPen(QColor(255, 255, 255), 4, Qt.PenStyle.DashLine))
                    else:
                        painter.setPen(QPen(QColor(200, 200, 200), 2, Qt.PenStyle.DashLine))
                
                # SELECTED PATHS - Colored solid (will be cut)
                else:
                    color = self.get_path_color(path, is_selected)
                    if is_selected:
                        painter.setPen(QPen(color, 4))
                    else:
                        painter.setPen(QPen(color, 2))
                
                for i in range(len(transformed) - 1):
                    painter.drawLine(transformed[i], transformed[i + 1])
                
                # Start point marker for selected path
                if is_selected:
                    painter.setBrush(QBrush(QColor(255, 255, 255)))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(transformed[0], 6, 6)
            
            # ANIMATING
            else:
                # Skip unselected paths in animation
                if not has_kerf_set:
                    continue
                
                color = self.get_path_color(path, is_selected)
                
                if path_idx < current_path_idx:
                    # Already completed - dim
                    dim_color = QColor(color.red(), color.green(), color.blue(), 80)
                    painter.setPen(QPen(dim_color, 1))
                    for i in range(len(transformed) - 1):
                        painter.drawLine(transformed[i], transformed[i + 1])
                
                elif path_idx == current_path_idx:
                    # Currently cutting
                    total_points = len(transformed)
                    path_progress = (total_paths * self.animation_progress) - current_path_idx
                    current_point = int(total_points * path_progress)
                    
                    # Uncut - very dim
                    painter.setPen(QPen(QColor(60, 60, 60), 1, Qt.PenStyle.DashLine))
                    for i in range(len(transformed) - 1):
                        painter.drawLine(transformed[i], transformed[i + 1])
                    
                    # Cut portion - bright
                    if current_point >= 1:
                        painter.setPen(QPen(color, 3))
                        for i in range(min(current_point, len(transformed) - 1)):
                            painter.drawLine(transformed[i], transformed[i + 1])
                        
                        # Torch at current position
                        if current_point < len(transformed):
                            torch_pos = transformed[min(current_point, len(transformed) - 1)]
                            
                            # Glow
                            gradient = QRadialGradient(torch_pos, 12)
                            gradient.setColorAt(0, QColor(255, 200, 0, 220))
                            gradient.setColorAt(0.5, QColor(255, 100, 0, 120))
                            gradient.setColorAt(1, QColor(255, 0, 0, 0))
                            painter.setBrush(QBrush(gradient))
                            painter.setPen(Qt.PenStyle.NoPen)
                            painter.drawEllipse(torch_pos, 12, 12)
                            
                            # Core
                            painter.setBrush(QBrush(QColor(255, 255, 255)))
                            painter.drawEllipse(torch_pos, 3, 3)
                
                else:
                    # Not yet cut - very dim
                    painter.setPen(QPen(QColor(40, 40, 40), 1, Qt.PenStyle.DashLine))
                    for i in range(len(transformed) - 1):
                        painter.drawLine(transformed[i], transformed[i + 1])
        
        # Info text
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        painter.setFont(QFont('Monospace', 9))
        
        if self.animate:
            selected_count = sum(1 for p in self.paths if 'kerf_type' in p and p['kerf_type'] in ['inside', 'outside', 'none'])
            info = f"Paths: {selected_count}/{len(self.paths)} | Cutting: {int(self.animation_progress * 100)}%"
        else:
            # Count kerf types
            outside = sum(1 for p in self.paths if p.get('kerf_type', '') == 'outside')
            inside = sum(1 for p in self.paths if p.get('kerf_type', '') == 'inside')
            none = sum(1 for p in self.paths if p.get('kerf_type', '') == 'none')
            unselected = len(self.paths) - outside - inside - none
            info = f"Paths: {len(self.paths)} | 🔴 Outside: {outside} | 🔵 Inside: {inside} | 🟢 No Kerf: {none} | ⚪ Unselected: {unselected}"
            
            if self.selected_path_idx is not None and self.selected_path_idx < len(self.paths):
                kerf = self.paths[self.selected_path_idx].get('kerf_type', 'unselected')
            else:
                kerf = 'unselected'
        
        painter.drawText(10, 20, info)
        
        # Instructions
        if not self.animate:
            painter.drawText(10, self.height() - 10, "Left-click: Select Path | Right-click: Set Kerf Type (unselected paths won't be cut)")

class FireBridgeCAM(QMainWindow):
    def __init__(self):
        super().__init__()
        self.lbl_stats = QLabel("")  # ensure exists
        self.setWindowTitle("FireBridge Plasma CAM - Professional Edition")
        self.setGeometry(100, 100, 1600, 900)
        
        self.filename = None
        self.paths = []
        self.toolpaths = []
        self.gcode_lines = []
        
        self.settings = {
            'post': 'fluidnc',
            'safe_z': 10.0,
            'pierce_height': 3.5,
            'cut_height': 1.5,
            'pierce_delay': 1.5,
            'feed': 2100,
            'power': 1000,
            'kerf': 1.2,
            'overcut_len': 0.0,
            'apply_kerf': True,
            'lead_in_type': 'line',
            'lead_out_type': 'line',
            'lead_in_len': 2.5,
            'lead_out_len': 2.5,
            'lead_in_angle': 30,
            'lead_out_angle': 30,
            'lead_arc_radius': 1.5,
            'corner_lead_distance': 2.5,  # NEW: Distance from corner for leads
            'touch_off': False,
            'touch_mode': 'per_cut',
            'probe_depth': 20,
            'probe_feed': 300,
            'retract': 1.5,
            'corner_slowdown': False,
            'slowdown_angle': 90,
            'slowdown_percent': 50,
            'small_hole_threshold': 12,
            'small_hole_feed_percent': 70,
            'chain_cutting': False,
            'chain_distance': 50.0,
            'thc_enable': True,
            'thc_disable_corners': True,
            'thc_corner_angle': 90,
            'thc_corner_distance': 2.0,
            'offset_x': 0.0,
            'offset_y': 0.0,
            'coolant_mode': 'off',
            'enable_path_sorting': True,
            'sort_holes_first': True,
            'sort_by_size': True,      
        }
        
        self.init_ui()
        self.load_settings_from_file()

    def debug_paths(self):
        """Show current path states for debugging"""
        msg = "CURRENT PATH STATES:\n\n"
        
        msg += f"Main paths: {len(self.paths)}\n"
        for i, p in enumerate(self.paths[:10]):  # Show first 10
            kerf = p.get('kerf_type', 'unassigned')
            if 'bounds' in p:
                b = p['bounds']
                msg += f"{i+1}. {b['width']:.1f}x{b['height']:.1f}mm - kerf: {kerf}\n"
            else:
                points = p.get('points', [])
                if points:
                    xs = [pt[0] for pt in points]
                    ys = [pt[1] for pt in points]
                    width = max(xs) - min(xs)
                    height = max(ys) - min(ys)
                    msg += f"{i+1}. {width:.1f}x{height:.1f}mm - kerf: {kerf}\n"
                else:
                    msg += f"{i+1}. No points - kerf: {kerf}\n"
        
        if len(self.paths) > 10:
            msg += f"... and {len(self.paths) - 10} more paths\n"
        
        if hasattr(self, 'canvas') and self.canvas.paths:
            msg += f"\nCanvas paths: {len(self.canvas.paths)}\n"
            for i, p in enumerate(self.canvas.paths[:10]):
                kerf = p.get('kerf_type', 'unassigned')
                points = p.get('points', [])
                if points:
                    xs = [pt[0] for pt in points]
                    ys = [pt[1] for pt in points]
                    width = max(xs) - min(xs)
                    height = max(ys) - min(ys)
                    msg += f"{i+1}. {width:.1f}x{height:.1f}mm - kerf: {kerf}\n"
                else:
                    msg += f"{i+1}. kerf: {kerf}\n"
        
        msg += f"\nToolpaths generated: {len(self.toolpaths)}\n"
        
        # Also print to console for detailed debugging
        print("\n" + "="*60)
        print("DEBUG PATHS - DETAILED OUTPUT")
        print("="*60)
        print(f"Main paths array: {len(self.paths)} paths")
        for i, p in enumerate(self.paths):
            kerf = p.get('kerf_type', 'unassigned')
            points = p.get('points', [])
            layer = p.get('layer', 'unknown')
            if points:
                xs = [pt[0] for pt in points]
                ys = [pt[1] for pt in points]
                width = max(xs) - min(xs)
                height = max(ys) - min(ys)
                center_x = (max(xs) + min(xs)) / 2
                center_y = (max(ys) + min(ys)) / 2
                
                # Try to identify shape
                shape = "unknown"
                if len(points) > 30 and abs(width - height) < 2.0:
                    shape = f"circle (Ø{(width+height)/2:.1f})"
                elif abs(width - height) < 0.1:
                    shape = "square"
                else:
                    shape = "rectangle"
                
                print(f"  Path {i+1}:")
                print(f"    Layer: {layer}")
                print(f"    Shape: {shape}")
                print(f"    Size: {width:.1f} x {height:.1f} mm")
                print(f"    Center: ({center_x:.1f}, {center_y:.1f})")
                print(f"    Points: {len(points)}")
                print(f"    Kerf: {kerf}")
                print(f"    Closed: {p.get('closed', False)}")
        
        QMessageBox.information(self, "Debug Info", msg)
    
    def remove_duplicate_points(self, path, tolerance=0.001):
        """Remove consecutive duplicate points from a path"""
        if not path or len(path) < 2:
            return path
        
        cleaned = [path[0]]  # Always keep first point
        
        for i in range(1, len(path)):
            # Calculate distance from last kept point
            dx = path[i][0] - cleaned[-1][0]
            dy = path[i][1] - cleaned[-1][1]
            dist = math.sqrt(dx*dx + dy*dy)
            
            # Only add if significantly different
            if dist > tolerance:
                cleaned.append(path[i])
        
        return cleaned
    
    def init_ui(self):
        main = QWidget()
        self.setCentralWidget(main)
        layout = QHBoxLayout(main)
        layout.setSpacing(8)
        
        # Three-column layout with improved sizing
        
        # LEFT: Controls (narrower)
        left = self.create_left_panel()
        left.setMaximumWidth(380)
        left.setMinimumWidth(350)
        layout.addWidget(left)
        
        # CENTER: Preview (square)
        center = self.create_center_panel()
        layout.addWidget(center, 1)
        
        # RIGHT: G-code (narrow)
        right = self.create_right_panel_improved()
        right.setMaximumWidth(350)
        right.setMinimumWidth(300)
        layout.addWidget(right)
    
    def create_center_panel(self):
        """Create centered square preview panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Preview controls
        controls = QHBoxLayout()
        
        lbl = QLabel("Preview")
        lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
        controls.addWidget(lbl)
        controls.addStretch()
        
        btn_fit = QPushButton("Fit View")
        btn_fit.clicked.connect(lambda: self.canvas.fit_to_view() if hasattr(self, 'canvas') else None)
        controls.addWidget(btn_fit)
        
        chk_leads = QCheckBox("Show Leads")
        chk_leads.setChecked(True)
        chk_leads.toggled.connect(lambda c: setattr(self.canvas, 'show_leads', c) if hasattr(self, 'canvas') else None)
        controls.addWidget(chk_leads)
        
        btn_animate = QPushButton("Animate")
        btn_animate.clicked.connect(lambda: self.canvas.start_animation() if hasattr(self, 'canvas') else None)
        controls.addWidget(btn_animate)
        
        layout.addLayout(controls)
        
        # Canvas - square aspect
        self.canvas = InteractivePreviewCanvas()
        self.canvas.setMinimumSize(500, 500)
        self.canvas.setStyleSheet("border: 2px solid #444;")
        self.canvas.kerf_changed.connect(self.on_kerf_changed)
        self.canvas.path_selected.connect(self.on_path_selected)
        layout.addWidget(self.canvas, 1)
        
        # Status bar
        self.status = QLabel("Ready")
        self.status.setStyleSheet("padding: 5px; background: #2a2a2a; border-radius: 3px;")
        layout.addWidget(self.status)
        
        return panel
    
    def create_right_panel_improved(self):
        """Create improved right panel with narrow G-code view"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Path layers table (compact)
        layers_group = QGroupBox("Path Layers")
        layers_layout = QVBoxLayout()
        
        self.tbl_layers = QTableWidget()
        self.tbl_layers.setColumnCount(4)
        self.tbl_layers.setHorizontalHeaderLabels(['#', 'Type', 'Kerf', 'Pts'])
        self.tbl_layers.horizontalHeader().setStretchLastSection(True)
        self.tbl_layers.setMaximumHeight(180)
        self.tbl_layers.setAlternatingRowColors(True)
        
        layers_layout.addWidget(self.tbl_layers)
        layers_group.setLayout(layers_layout)
        layout.addWidget(layers_group)
        
        # G-code output (narrow, monospace)
        gcode_group = QGroupBox("G-code Output")
        gcode_layout = QVBoxLayout()
        
        self.txt_gcode = QTextEdit()
        self.txt_gcode.setReadOnly(True)
        self.txt_gcode.setFont(QFont("Courier", 9))
        self.txt_gcode.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a0a;
                color: #00ff00;
                border: 1px solid #444;
                font-family: 'Courier New', monospace;
                line-height: 1.2;
            }
        """)
        
        gcode_layout.addWidget(self.txt_gcode)
        gcode_group.setLayout(gcode_layout)
        layout.addWidget(gcode_group, 1)
        
        return panel
    
    def create_left_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(5)
        
        # File section
        file_group = QGroupBox("File")
        file_layout = QVBoxLayout()
        
        btn_load = QPushButton("📁 Load CAD File (SVG/DXF)")
        btn_load.clicked.connect(self.load_file)
        btn_load.setMinimumHeight(35)
        file_layout.addWidget(btn_load)
        
        self.lbl_file = QLabel("No file loaded")
        self.lbl_file.setWordWrap(True)
        self.lbl_file.setStyleSheet("color: #888; padding: 5px;")
        file_layout.addWidget(self.lbl_file)
        
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)
        
        # Settings tabs in scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        tabs_widget = QWidget()
        tabs_layout = QVBoxLayout(tabs_widget)
        
        tabs = QTabWidget()
        tabs.addTab(self.create_machine_tab(), "Machine")
        tabs.addTab(self.create_plasma_tab(), "Plasma")
        tabs.addTab(self.create_leads_tab(), "Leads")
        tabs.addTab(self.create_offset_tab(), "XY Offset")
        tabs.addTab(self.create_advanced_tab(), "Advanced")
        tabs.addTab(self.create_material_tab(), "Materials")
        
        tabs_layout.addWidget(tabs)
        scroll.setWidget(tabs_widget)
        layout.addWidget(scroll)
        
        # Action buttons
        btn_generate = QPushButton("⚡ Generate Toolpaths")
        btn_generate.setStyleSheet("QPushButton { background-color: #10b981; color: white; font-weight: bold; padding: 8px; }")
        btn_generate.clicked.connect(self.generate_toolpaths)
        layout.addWidget(btn_generate)
        
        btn_gcode = QPushButton("🔧 Generate G-code")
        btn_gcode.setStyleSheet("QPushButton { background-color: #8b5cf6; color: white; font-weight: bold; padding: 8px; }")
        btn_gcode.clicked.connect(self.generate_gcode)
        layout.addWidget(btn_gcode)
        
        btn_debug = QPushButton("🔍 Debug Paths")
        btn_debug.clicked.connect(self.debug_paths)
        layout.addWidget(btn_debug)
        
        btn_save = QPushButton("💾 Save G-code")
        btn_save.clicked.connect(self.save_gcode)
        layout.addWidget(btn_save)
        
        return panel
    
    def debug_paths(self):
        """Show current path states"""
        msg = "CURRENT PATH STATES:\n\n"
        
        msg += f"Main paths: {len(self.paths)}\n"
        for i, p in enumerate(self.paths[:10]):  # Show first 10
            kerf = p.get('kerf_type', 'unassigned')
            if 'bounds' in p:
                b = p['bounds']
                msg += f"{i+1}. {b['width']:.1f}x{b['height']:.1f}mm - kerf: {kerf}\n"
            else:
                msg += f"{i+1}. {len(p.get('points', []))} points - kerf: {kerf}\n"
        
        if hasattr(self, 'canvas') and self.canvas.paths:
            msg += f"\nCanvas paths: {len(self.canvas.paths)}\n"
            for i, p in enumerate(self.canvas.paths[:10]):
                kerf = p.get('kerf_type', 'unassigned')
                msg += f"{i+1}. kerf: {kerf}\n"
        
        QMessageBox.information(self, "Debug Info", msg)
    
    def create_machine_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        layout.addWidget(QLabel("Post-Processor:"))
        self.cmb_post = QComboBox()
        for key, val in POST_PROCESSORS.items():
            self.cmb_post.addItem(val['name'], key)
        layout.addWidget(self.cmb_post)
        
        layout.addWidget(QLabel("Safe Z (mm):"))
        self.spin_safe_z = QDoubleSpinBox()
        self.spin_safe_z.setRange(0, 100)
        self.spin_safe_z.setValue(10)
        self.spin_safe_z.setSingleStep(0.5)
        layout.addWidget(self.spin_safe_z)
        
        # TOUCH-OFF SECTION
        layout.addWidget(QLabel("<b>Touch-Off Probing:</b>"))
        
        self.chk_touch_off = QCheckBox("Enable Touch-Off (G38.2)")
        self.chk_touch_off.setStyleSheet("""
            QCheckBox {
                color: #ffffff;
                background-color: transparent;
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                background-color: #2a2a2a;
                border: 1px solid #666;
            }
            QCheckBox::indicator:checked {
                background-color: #2563eb;
            }
        """)
        layout.addWidget(self.chk_touch_off)
        
        layout.addWidget(QLabel("Touch-Off Mode:"))
        self.cmb_touch_mode = QComboBox()
        self.cmb_touch_mode.addItems(['per_cut', 'once_job', 'holes_only'])
        layout.addWidget(self.cmb_touch_mode)
        
        layout.addWidget(QLabel("Probe Depth (mm):"))
        self.spin_probe_depth = QDoubleSpinBox()
        self.spin_probe_depth.setRange(1, 50)
        self.spin_probe_depth.setValue(20)
        layout.addWidget(self.spin_probe_depth)
        
        layout.addWidget(QLabel("Probe Feed (mm/min):"))
        self.spin_probe_feed = QSpinBox()
        self.spin_probe_feed.setRange(50, 1000)
        self.spin_probe_feed.setValue(300)
        layout.addWidget(self.spin_probe_feed)
        
        layout.addWidget(QLabel("Retract After Probe (mm):"))
        self.spin_retract = QDoubleSpinBox()
        self.spin_retract.setRange(0, 10)
        self.spin_retract.setValue(1.5)
        layout.addWidget(self.spin_retract)
        
        # THC Controls
        layout.addWidget(QLabel("<b>THC (Torch Height Control):</b>"))
        
        self.chk_thc = QCheckBox("Enable THC")
        self.chk_thc.setChecked(True)
        self.chk_thc.setStyleSheet("QCheckBox { color: #ffffff; background: transparent; }")
        
        # With this:
        self.chk_thc = QCheckBox("Enable THC")
        self.chk_thc.setChecked(True)
        self.chk_thc.setStyleSheet("""
            QCheckBox {
                color: #ffffff;
                background-color: transparent;
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                background-color: #2a2a2a;
                border: 1px solid #666;
            }
            QCheckBox::indicator:checked {
                background-color: #2563eb;
            }
        """)
        layout.addWidget(self.chk_thc)
        
        # Coolant control
        layout.addWidget(QLabel("<b>Coolant:</b>"))
        self.combo_coolant = QComboBox()
        self.combo_coolant.addItems(["Off", "Mist (M7)", "Flood (M8)"])
        layout.addWidget(self.combo_coolant)
        
        self.chk_thc_corners = QCheckBox("Disable THC at Corners")
        self.chk_thc_corners.setChecked(True)
        self.chk_thc_corners.setStyleSheet("""
            QCheckBox {
                color: #ffffff;
                background-color: transparent;
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                background-color: #2a2a2a;
                border: 1px solid #666;
            }
            QCheckBox::indicator:checked {
                background-color: #2563eb;
            }
        """)
        layout.addWidget(self.chk_thc_corners)
        
        layout.addWidget(QLabel("Corner Angle Threshold (degrees):"))
        self.spin_corner_angle = QSpinBox()
        self.spin_corner_angle.setRange(0, 180)
        self.spin_corner_angle.setValue(90)
        layout.addWidget(self.spin_corner_angle)
        
        layout.addWidget(QLabel("Corner Distance (mm):"))
        self.spin_corner_dist = QDoubleSpinBox()
        self.spin_corner_dist.setRange(0.1, 10)
        self.spin_corner_dist.setValue(2.0)
        self.spin_corner_dist.setSingleStep(0.5)
        layout.addWidget(self.spin_corner_dist)
        
        layout.addStretch()
        return tab
    
    def create_plasma_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        layout.addWidget(QLabel("Pierce Height (mm):"))
        self.spin_pierce_height = QDoubleSpinBox()
        self.spin_pierce_height.setRange(0, 10)
        self.spin_pierce_height.setValue(3.5)
        self.spin_pierce_height.setSingleStep(0.1)
        layout.addWidget(self.spin_pierce_height)
        
        layout.addWidget(QLabel("Cut Height (mm):"))
        self.spin_cut_height = QDoubleSpinBox()
        self.spin_cut_height.setRange(0, 10)
        self.spin_cut_height.setValue(1.5)
        self.spin_cut_height.setSingleStep(0.1)
        layout.addWidget(self.spin_cut_height)
        
        layout.addWidget(QLabel("Pierce Delay (sec):"))
        self.spin_pierce_delay = QDoubleSpinBox()
        self.spin_pierce_delay.setRange(0, 5)
        self.spin_pierce_delay.setValue(1.5)
        self.spin_pierce_delay.setSingleStep(0.1)
        layout.addWidget(self.spin_pierce_delay)
        
        layout.addWidget(QLabel("Feed Rate (mm/min):"))
        self.spin_feed = QSpinBox()
        self.spin_feed.setRange(100, 10000)
        self.spin_feed.setValue(2100)
        self.spin_feed.setSingleStep(100)
        layout.addWidget(self.spin_feed)
        
        layout.addWidget(QLabel("Power (S value):"))
        self.spin_power = QSpinBox()
        self.spin_power.setRange(0, 1000)
        self.spin_power.setValue(1000)
        layout.addWidget(self.spin_power)
        
        layout.addWidget(QLabel("Kerf Width (mm):"))
        self.spin_kerf = QDoubleSpinBox()
        self.spin_kerf.setRange(0, 5)
        self.spin_kerf.setValue(1.2)
        self.spin_kerf.setSingleStep(0.1)
        layout.addWidget(self.spin_kerf)
        
        # ADDED: Overcut Length Input
        layout.addWidget(QLabel("Overcut Length (mm):"))
        self.spin_overcut = QDoubleSpinBox()
        self.spin_overcut.setRange(0, 10)
        self.spin_overcut.setValue(0.0)
        self.spin_overcut.setSingleStep(0.5)
        layout.addWidget(self.spin_overcut)
        
        self.chk_apply_kerf = QCheckBox("Apply Kerf Compensation")
        self.chk_apply_kerf.setChecked(True)
        self.chk_apply_kerf.setStyleSheet("QCheckBox { color: #e0e0e0; }")
        layout.addWidget(self.chk_apply_kerf)
        
        # Path Sorting Section
        layout.addWidget(QLabel("<b>Path Sorting:</b>"))
        
        self.chk_path_sorting = QCheckBox("Enable Smart Path Sorting")
        self.chk_path_sorting.setChecked(True)
        self.chk_path_sorting.setStyleSheet("QCheckBox { color: #e0e0e0; }")
        layout.addWidget(self.chk_path_sorting)
        
        self.chk_holes_first = QCheckBox("Cut Holes Before Perimeters (Inside-Out)")
        self.chk_holes_first.setChecked(True)
        self.chk_holes_first.setStyleSheet("QCheckBox { color: #e0e0e0; }")
        layout.addWidget(self.chk_holes_first)
        
        self.chk_sort_by_size = QCheckBox("Sort Holes by Size (Smallest First)")
        self.chk_sort_by_size.setChecked(True)
        self.chk_sort_by_size.setStyleSheet("QCheckBox { color: #e0e0e0; }")
        layout.addWidget(self.chk_sort_by_size)
        
        layout.addStretch()
        return tab
    
    def create_leads_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        layout.addWidget(QLabel("Lead-In Type:"))
        self.cmb_lead_in = QComboBox()
        self.cmb_lead_in.addItems(['none', 'line', 'arc'])
        self.cmb_lead_in.setCurrentText('line')
        layout.addWidget(self.cmb_lead_in)
        
        layout.addWidget(QLabel("Lead-In Length (mm):"))
        self.spin_lead_in_len = QDoubleSpinBox()
        self.spin_lead_in_len.setRange(0, 20)
        self.spin_lead_in_len.setValue(2.5)
        self.spin_lead_in_len.setSingleStep(0.5)
        layout.addWidget(self.spin_lead_in_len)
        
        layout.addWidget(QLabel("Lead-In Angle (degrees):"))
        self.spin_lead_in_angle = QSpinBox()
        self.spin_lead_in_angle.setRange(0, 90)
        self.spin_lead_in_angle.setValue(30)
        layout.addWidget(self.spin_lead_in_angle)
        
        # NEW: Corner lead distance setting
        layout.addWidget(QLabel("Distance from Corner (mm):"))
        self.spin_corner_lead_distance = QDoubleSpinBox()
        self.spin_corner_lead_distance.setRange(0.5, 10.0)
        self.spin_corner_lead_distance.setValue(2.5)  # Industry standard
        self.spin_corner_lead_distance.setSingleStep(0.5)
        self.spin_corner_lead_distance.setToolTip(
            "Typical: 1.5-2mm (thin), 2-3mm (medium), 3-5mm (thick material)"
        )
        layout.addWidget(self.spin_corner_lead_distance)
        
        layout.addWidget(QLabel("Lead-Out Type:"))
        self.cmb_lead_out = QComboBox()
        self.cmb_lead_out.addItems(['none', 'line', 'arc'])
        self.cmb_lead_out.setCurrentText('line')
        layout.addWidget(self.cmb_lead_out)
        
        layout.addWidget(QLabel("Lead-Out Length (mm):"))
        self.spin_lead_out_len = QDoubleSpinBox()
        self.spin_lead_out_len.setRange(0, 20)
        self.spin_lead_out_len.setValue(2.5)
        self.spin_lead_out_len.setSingleStep(0.5)
        layout.addWidget(self.spin_lead_out_len)
        
        layout.addWidget(QLabel("Lead-Out Angle (degrees):"))
        self.spin_lead_out_angle = QSpinBox()
        self.spin_lead_out_angle.setRange(0, 90)
        self.spin_lead_out_angle.setValue(30)
        layout.addWidget(self.spin_lead_out_angle)
        
        layout.addWidget(QLabel("Arc Lead Radius (mm):"))
        self.spin_arc_radius = QDoubleSpinBox()
        self.spin_arc_radius.setRange(0.5, 10)
        self.spin_arc_radius.setValue(1.5)
        layout.addWidget(self.spin_arc_radius)
        
        layout.addStretch()
        return tab
    
    def create_offset_tab(self):
        """Create XY offset controls"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        layout.addWidget(QLabel("<b>Work Offset (G54)</b>"))
        
        layout.addWidget(QLabel("X Offset (mm):"))
        self.spin_offset_x = QDoubleSpinBox()
        self.spin_offset_x.setRange(-1000, 1000)
        self.spin_offset_x.setValue(0.0)
        self.spin_offset_x.setSingleStep(1.0)
        self.spin_offset_x.setDecimals(3)
        layout.addWidget(self.spin_offset_x)
        
        layout.addWidget(QLabel("Y Offset (mm):"))
        self.spin_offset_y = QDoubleSpinBox()
        self.spin_offset_y.setRange(-1000, 1000)
        self.spin_offset_y.setValue(0.0)
        self.spin_offset_y.setSingleStep(1.0)
        self.spin_offset_y.setDecimals(3)
        layout.addWidget(self.spin_offset_y)
        
        # Quick preset buttons
        layout.addWidget(QLabel("<b>Quick Presets:</b>"))
        
        btn_layout = QHBoxLayout()
        
        btn_zero = QPushButton("Zero (0, 0)")
        btn_zero.clicked.connect(lambda: self.set_offset_preset(0, 0))
        btn_layout.addWidget(btn_zero)
        
        btn_center = QPushButton("Center Table")
        btn_center.clicked.connect(self.set_offset_to_center)
        btn_layout.addWidget(btn_center)
        
        layout.addLayout(btn_layout)
        
        layout.addWidget(QLabel("<i>Offsets are applied to all toolpaths</i>"))
        
        layout.addStretch()
        return tab
    
    def set_offset_preset(self, x, y):
        """Set offset to preset values"""
        self.spin_offset_x.setValue(x)
        self.spin_offset_y.setValue(y)
    
    def set_offset_to_center(self):
        """Center the part on the table (assumes 500x500mm table)"""
        if not self.paths:
            QMessageBox.warning(self, "No Paths", "Load an SVG file first!")
            return
        
        # Find bounding box
        all_points = []
        for path in self.paths:
            all_points.extend(path.get('points', []))
        
        if not all_points:
            return
        
        xs = [p[0] for p in all_points]
        ys = [p[1] for p in all_points]
        
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        
        width = max_x - min_x
        height = max_y - min_y
        
        # Center on 250, 250 (middle of 500x500 table)
        center_x = 250 - (min_x + width / 2)
        center_y = 250 - (min_y + height / 2)
        
        self.spin_offset_x.setValue(center_x)
        self.spin_offset_y.setValue(center_y)
    
    def create_advanced_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # --- CORNER SLOWDOWN ---
        self.chk_corner_slow = QCheckBox("Corner Slowdown")
        self.chk_corner_slow.setStyleSheet("QCheckBox { color: #e0e0e0; }")
        layout.addWidget(self.chk_corner_slow)
        
        layout.addWidget(QLabel("Slowdown Angle (deg):"))
        self.spin_slow_angle = QSpinBox()
        self.spin_slow_angle.setRange(0, 180)
        self.spin_slow_angle.setValue(90)
        layout.addWidget(self.spin_slow_angle)
        
        layout.addWidget(QLabel("Slowdown % of Feed:"))
        self.spin_slow_percent = QSpinBox()
        self.spin_slow_percent.setRange(10, 100)
        self.spin_slow_percent.setValue(50)
        layout.addWidget(self.spin_slow_percent)
        
        # --- SMALL HOLE SETTINGS ---
        layout.addWidget(QLabel("Small Hole Threshold (mm):"))
        self.spin_hole_threshold = QDoubleSpinBox()
        self.spin_hole_threshold.setRange(0, 50)
        self.spin_hole_threshold.setValue(12)
        layout.addWidget(self.spin_hole_threshold)
        
        layout.addWidget(QLabel("Small Hole Feed %:"))
        self.spin_hole_feed = QSpinBox()
        self.spin_hole_feed.setRange(10, 100)
        self.spin_hole_feed.setValue(70)
        layout.addWidget(self.spin_hole_feed)
        
        # --- CHAIN CUTTING ---
        self.chk_chain = QCheckBox("Enable Chain Cutting")
        self.chk_chain.setStyleSheet("QCheckBox { color: #e0e0e0; }")
        layout.addWidget(self.chk_chain)
        
        layout.addWidget(QLabel("Chain Cut Max Distance (mm):"))
        self.spin_chain_dist = QDoubleSpinBox()
        self.spin_chain_dist.setRange(0, 500)
        self.spin_chain_dist.setValue(50.0)
        self.spin_chain_dist.setSingleStep(5.0)
        layout.addWidget(self.spin_chain_dist)
        
        layout.addStretch()
        return tab
    
    def create_material_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        layout.addWidget(QLabel("Material Presets:"))
        
        self.cmb_material = QComboBox()
        self.cmb_material.addItem("-- Custom --")
        for name in MATERIAL_PRESETS.keys():
            self.cmb_material.addItem(name)
        self.cmb_material.currentTextChanged.connect(self.load_material_preset)
        layout.addWidget(self.cmb_material)
        
        btn_apply = QPushButton("Apply Preset")
        btn_apply.clicked.connect(self.apply_material_preset)
        layout.addWidget(btn_apply)
        
        layout.addWidget(QLabel("Preset Values:"))
        self.txt_preset_info = QTextEdit()
        self.txt_preset_info.setReadOnly(True)
        self.txt_preset_info.setMaximumHeight(150)
        layout.addWidget(self.txt_preset_info)
        
        layout.addStretch()
        return tab
    
    def load_material_preset(self, name):
        if name in MATERIAL_PRESETS:
            preset = MATERIAL_PRESETS[name]
            info = f"Pierce Height: {preset['pierce_height']} mm\n"
            info += f"Cut Height: {preset['cut_height']} mm\n"
            info += f"Pierce Delay: {preset['pierce_delay']} sec\n"
            info += f"Feed Rate: {preset['feed']} mm/min\n"
            info += f"Kerf: {preset['kerf']} mm"
            self.txt_preset_info.setText(info)
        else:
            self.txt_preset_info.setText("Custom settings")
    
    def apply_material_preset(self):
        name = self.cmb_material.currentText()
        if name in MATERIAL_PRESETS:
            preset = MATERIAL_PRESETS[name]
            self.spin_pierce_height.setValue(preset['pierce_height'])
            self.spin_cut_height.setValue(preset['cut_height'])
            self.spin_pierce_delay.setValue(preset['pierce_delay'])
            self.spin_feed.setValue(preset['feed'])
            self.spin_kerf.setValue(preset['kerf'])
            QMessageBox.information(self, "Success", f"Applied preset: {name}")
    
    def create_right_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        tabs = QTabWidget()
        
        # Preview tab
        preview_tab = QWidget()
        preview_layout = QVBoxLayout(preview_tab)
        
        self.lbl_stats = QLabel("Load a file to see statistics")
        preview_layout.addWidget(self.lbl_stats)
        
        # Interactive preview canvas
        self.canvas = InteractivePreviewCanvas()
        self.canvas.kerf_changed.connect(self.on_kerf_changed)
        self.canvas.path_selected.connect(self.on_path_selected)
        preview_layout.addWidget(self.canvas)
        
        # Preview controls
        controls = QHBoxLayout()
        
        btn_fit = QPushButton("Fit to View")
        btn_fit.clicked.connect(self.canvas.fit_to_view)
        controls.addWidget(btn_fit)
        
        btn_animate = QPushButton("▶ Animate Cut")
        btn_animate.clicked.connect(self.canvas.start_animation)
        controls.addWidget(btn_animate)
        
        btn_stop = QPushButton("⏹ Stop")
        btn_stop.clicked.connect(self.canvas.stop_animation)
        controls.addWidget(btn_stop)
        
        controls.addStretch()
        preview_layout.addLayout(controls)
        
        tabs.addTab(preview_tab, "Preview")
        
        # G-code tab
        gcode_tab = QWidget()
        gcode_layout = QVBoxLayout(gcode_tab)
        
        self.txt_gcode = QTextEdit()
        self.txt_gcode.setReadOnly(True)
        self.txt_gcode.setStyleSheet("QTextEdit { font-family: 'Courier New', monospace; font-size: 10pt; }")
        gcode_layout.addWidget(self.txt_gcode)
        
        tabs.addTab(gcode_tab, "G-code")
        
        # Layer table tab
        layer_tab = QWidget()
        layer_layout = QVBoxLayout(layer_tab)
        
        self.tbl_layers = QTableWidget()
        self.tbl_layers.setColumnCount(4)
        self.tbl_layers.setHorizontalHeaderLabels(['Layer', 'Kerf Type', 'Count', 'Order'])
        self.tbl_layers.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layer_layout.addWidget(self.tbl_layers)
        
        tabs.addTab(layer_tab, "Layers")
        
        layout.addWidget(tabs)
        return panel
    
    def on_path_selected(self, idx):
        """Handle path selection event"""
        if idx < len(self.paths):
            kerf = self.paths[idx].get('kerf_type', 'outside')
            print(f"Path {idx + 1} selected - Kerf type: {kerf}")
    
    def on_kerf_changed(self):
        """Handle kerf type change from canvas"""
        print("Kerf type changed via canvas - regenerate toolpaths to apply")
    
    def save_settings_to_file(self):
        """Save current settings to JSON file"""
        try:
            settings_file = os.path.join(os.path.expanduser("~"), ".firebridge_settings.json")
            with open(settings_file, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Failed to save settings: {e}")
    
    def load_settings_from_file(self):
        """Load settings from JSON file"""
        try:
            settings_file = os.path.join(os.path.expanduser("~"), ".firebridge_settings.json")
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    loaded = json.load(f)
                    self.settings.update(loaded)
                    self.load_ui_from_settings()
                    print("Settings loaded successfully")
        except Exception as e:
            print(f"Failed to load settings: {e}")
    
    def load_ui_from_settings(self):
        """Load settings into UI controls"""
        self.cmb_post.setCurrentIndex(self.cmb_post.findData(self.settings.get('post', 'fluidnc')))
        self.spin_safe_z.setValue(self.settings.get('safe_z', 10.0))
        self.spin_pierce_height.setValue(self.settings.get('pierce_height', 3.5))
        self.spin_cut_height.setValue(self.settings.get('cut_height', 1.5))
        self.spin_pierce_delay.setValue(self.settings.get('pierce_delay', 1.5))
        self.spin_feed.setValue(self.settings.get('feed', 2100))
        self.spin_power.setValue(self.settings.get('power', 1000))
        self.spin_kerf.setValue(self.settings.get('kerf', 1.2))
        self.spin_overcut.setValue(self.settings.get('overcut_len', 0.0))
        self.chk_apply_kerf.setChecked(self.settings.get('apply_kerf', True))
        
        self.cmb_lead_in.setCurrentText(self.settings.get('lead_in_type', 'line'))
        self.cmb_lead_out.setCurrentText(self.settings.get('lead_out_type', 'line'))
        self.spin_lead_in_len.setValue(self.settings.get('lead_in_len', 2.5))
        self.spin_lead_out_len.setValue(self.settings.get('lead_out_len', 2.5))
        self.spin_lead_in_angle.setValue(self.settings.get('lead_in_angle', 30))
        self.spin_lead_out_angle.setValue(self.settings.get('lead_out_angle', 30))
        self.spin_arc_radius.setValue(self.settings.get('lead_arc_radius', 1.5))
        self.spin_corner_lead_distance.setValue(self.settings.get('corner_lead_distance', 2.5))
        
        self.chk_touch_off.setChecked(self.settings.get('touch_off', False))
        self.cmb_touch_mode.setCurrentText(self.settings.get('touch_mode', 'per_cut'))
        self.spin_probe_depth.setValue(self.settings.get('probe_depth', 20.0))
        self.spin_probe_feed.setValue(self.settings.get('probe_feed', 300))
        self.spin_retract.setValue(self.settings.get('retract', 1.5))
        
        self.chk_corner_slow.setChecked(self.settings.get('corner_slowdown', False))
        self.spin_slow_angle.setValue(self.settings.get('slowdown_angle', 90))
        self.spin_slow_percent.setValue(self.settings.get('slowdown_percent', 50))
        
        self.spin_hole_threshold.setValue(self.settings.get('small_hole_threshold', 12.0))
        self.spin_hole_feed.setValue(self.settings.get('small_hole_feed_percent', 70))
        
        self.chk_chain.setChecked(self.settings.get('chain_cutting', False))
        self.spin_chain_dist.setValue(self.settings.get('chain_distance', 50.0))
        
        self.chk_thc.setChecked(self.settings.get('thc_enable', True))
        self.chk_thc_corners.setChecked(self.settings.get('thc_disable_corners', True))
        self.spin_corner_angle.setValue(self.settings.get('thc_corner_angle', 90))
        self.spin_corner_dist.setValue(self.settings.get('thc_corner_distance', 2.0))
        
        self.spin_offset_x.setValue(self.settings.get('offset_x', 0.0))
        self.spin_offset_y.setValue(self.settings.get('offset_y', 0.0))
    
    def update_settings_from_ui(self):
        self.settings['post'] = self.cmb_post.currentData()
        self.settings['safe_z'] = self.spin_safe_z.value()
        self.settings['pierce_height'] = self.spin_pierce_height.value()
        self.settings['cut_height'] = self.spin_cut_height.value()
        self.settings['pierce_delay'] = self.spin_pierce_delay.value()
        self.settings['feed'] = self.spin_feed.value()
        self.settings['power'] = self.spin_power.value()
        self.settings['kerf'] = self.spin_kerf.value()
        self.settings['overcut_len'] = self.spin_overcut.value()
        self.settings['apply_kerf'] = self.chk_apply_kerf.isChecked()
        self.settings['lead_in_type'] = self.cmb_lead_in.currentText()
        self.settings['lead_out_type'] = self.cmb_lead_out.currentText()
        self.settings['lead_in_len'] = self.spin_lead_in_len.value()
        self.settings['lead_out_len'] = self.spin_lead_out_len.value()
        self.settings['lead_in_angle'] = self.spin_lead_in_angle.value()
        self.settings['lead_out_angle'] = self.spin_lead_out_angle.value()
        self.settings['lead_arc_radius'] = self.spin_arc_radius.value()
        self.settings['corner_lead_distance'] = self.spin_corner_lead_distance.value()
        self.settings['touch_off'] = self.chk_touch_off.isChecked()
        self.settings['touch_mode'] = self.cmb_touch_mode.currentText()
        self.settings['probe_depth'] = self.spin_probe_depth.value()
        self.settings['probe_feed'] = self.spin_probe_feed.value()
        self.settings['retract'] = self.spin_retract.value()
        self.settings['corner_slowdown'] = self.chk_corner_slow.isChecked()
        self.settings['slowdown_angle'] = self.spin_slow_angle.value()
        self.settings['slowdown_percent'] = self.spin_slow_percent.value()
        self.settings['small_hole_threshold'] = self.spin_hole_threshold.value()
        self.settings['small_hole_feed_percent'] = self.spin_hole_feed.value()
        self.settings['chain_cutting'] = self.chk_chain.isChecked()
        self.settings['chain_distance'] = self.spin_chain_dist.value()
        self.settings['thc_enable'] = self.chk_thc.isChecked()
        self.settings['thc_disable_corners'] = self.chk_thc_corners.isChecked()
        self.settings['thc_corner_angle'] = self.spin_corner_angle.value()
        self.settings['thc_corner_distance'] = self.spin_corner_dist.value()
        self.settings['offset_x'] = self.spin_offset_x.value()
        self.settings['offset_y'] = self.spin_offset_y.value()
        
        # Auto-save settings
        self.save_settings_to_file()
        
        # Coolant
        coolant_text = self.combo_coolant.currentText()
        if "Mist" in coolant_text:
            self.settings['coolant_mode'] = 'mist'
        elif "Flood" in coolant_text:
            self.settings['coolant_mode'] = 'flood'
        else:
            self.settings['coolant_mode'] = 'off'
    
    def load_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, 
            "Open File", 
            "", 
            "CAD Files (*.dxf *.svg);;DXF Files (*.dxf);;SVG Files (*.svg);;All Files (*.*)"
        )
        if filename:
            self.filename = filename
            self.lbl_file.setText(Path(filename).name)
            
            # Parse based on file extension
            ext = Path(filename).suffix.lower()
            if ext == '.dxf':
                self.parse_dxf()
            elif ext == '.svg':
                self.parse_svg()
            else:
                QMessageBox.warning(self, "Unknown Format", f"Cannot parse {ext} files")
    
    def parse_dxf(self):
        """Robust DXF parser"""
        self.paths = []
        
        with open(self.filename, 'r', encoding='utf-8', errors='ignore') as f:
            lines = [l.strip() for l in f.readlines()]
        
        i = 0
        entities = []
        current = None
        section = None
        
        while i < len(lines):
            if i+1 >= len(lines):
                break
            
            code = lines[i]
            value = lines[i+1]
            i += 2
            
            if code == '0':
                if value == 'SECTION':
                    section = 'SECTION'
                elif value == 'ENDSEC':
                    section = None
                elif value == 'EOF':
                    break
                elif section == 'ENTITIES':
                    if current:
                        entities.append(current)
                    current = {'type': value, 'data': {}}
            elif code == '2' and section == 'SECTION':
                section = value
            elif current:
                current['data'][code] = value
        
        if current:
            entities.append(current)
        
        # Convert to paths
        poly_verts = []
        poly_layer = ''
        poly_closed = False
        
        for ent in entities:
            t = ent['type']
            d = ent['data']
            
            if t == 'POLYLINE':
                poly_verts = []
                poly_layer = d.get('8', '0')
                poly_closed = (int(d.get('70', '0')) & 1) != 0
            
            elif t == 'VERTEX':
                x = float(d.get('10', 0))
                y = float(d.get('20', 0))
                poly_verts.append((x, y))
            
            elif t == 'SEQEND':
                if poly_verts:
                    if poly_closed and len(poly_verts) > 2:
                        if poly_verts[0] != poly_verts[-1]:
                            poly_verts.append(poly_verts[0])
                    
                    self.paths.append({
                        'points': poly_verts[:],
                        'closed': poly_closed,
                        'layer': poly_layer,
                    })
                poly_verts = []
                                                    
            elif t == 'CIRCLE':
                cx = float(d.get('10', 0))
                cy = float(d.get('20', 0))
                r = float(d.get('40', 0))
                pts = []
                for i in range(37):
                    a = (i / 36) * 2 * math.pi
                    pts.append((cx + r*math.cos(a), cy + r*math.sin(a)))
                self.paths.append({
                    'points': pts,
                    'closed': True,
                    'layer': d.get('8', '0'),
                })
            
            elif t == 'ELLIPSE':
                cx = float(d.get('10', 0))
                cy = float(d.get('20', 0))
                mx = float(d.get('11', 0))
                my = float(d.get('21', 0))
                ratio = float(d.get('40', 1))
                start = float(d.get('41', 0))
                end = float(d.get('42', 2*math.pi))
                
                maj = math.sqrt(mx*mx + my*my)
                minor = maj * ratio
                rot = math.atan2(my, mx)
                
                pts = []
                for i in range(37):
                    t_param = start + (end - start) * (i / 36)
                    xl = maj * math.cos(t_param)
                    yl = minor * math.sin(t_param)
                    x = cx + xl*math.cos(rot) - yl*math.sin(rot)
                    y = cy + xl*math.sin(rot) + yl*math.cos(rot)
                    pts.append((x, y))
                
                self.paths.append({
                    'points': pts,
                    'closed': abs(end - start - 2*math.pi) < 0.01,
                    'layer': d.get('8', '0'),
                })
        
        # Update UI after DXF parsing
        layers = {}
        for p in self.paths:
            l = p['layer']
            layers[l] = layers.get(l, 0) + 1
        
        stats = f"Loaded {len(self.paths)} paths from DXF\n"
        for l, c in layers.items():
            stats += f"  {l}: {c}\n"
        self.lbl_stats.setText(stats)
        
        self.update_layer_table(layers)
        self.canvas.set_paths(self.paths)
    
    def parse_svg(self):
        """Parse SVG file and extract paths"""
        self.paths = []
        
        try:
            tree = ET.parse(self.filename)
            root = tree.getroot()
            
            ns = {'svg': 'http://www.w3.org/2000/svg'}
            
            viewbox = root.get('viewBox')
            if viewbox:
                vb = [float(x) for x in viewbox.split()]
                offset_x, offset_y = vb[0], vb[1]
            else:
                offset_x, offset_y = 0, 0
            
            # Parse all path elements
            for path_elem in root.findall('.//svg:path', ns) + root.findall('.//path'):
                d = path_elem.get('d')
                if not d:
                    continue
                
                # Split path data by Move commands to separate disconnected shapes
                import re
                subpaths = re.split(r'(?=[Mm])', d)
                subpaths = [sp.strip() for sp in subpaths if sp.strip()]
                
                for idx, subpath in enumerate(subpaths):
                    if not subpath:
                        continue
                    
                    points = self.parse_svg_path(subpath)
                    if len(points) > 1:
                        closed = (abs(points[0][0] - points[-1][0]) < 0.01 and 
                                 abs(points[0][1] - points[-1][1]) < 0.01)
                        
                        layer = path_elem.get('id', f'Layer_0_sub{idx}')
                        self.paths.append({
                            'points': points,
                            'closed': closed,
                            'layer': layer,
                        })
            
            # Print loaded paths info (console)
            print(f"Loaded {len(self.paths)} paths from SVG")
            for i, path in enumerate(self.paths):
                print(f"  {path.get('layer', 'Unknown')}: {len(path['points'])} points")
            
            # Update canvas
            self.canvas.set_paths(self.paths)
            
            # Update UI stats (if label exists)
            if hasattr(self, 'lbl_stats'):
                layers = {}
                for p in self.paths:
                    l = p.get('layer', 'Unknown')
                    layers[l] = layers.get(l, 0) + 1
                
                stats = f"Loaded {len(self.paths)} paths from SVG\n"
                for l, c in layers.items():
                    stats += f"  {l}: {c}\n"
                self.lbl_stats.setText(stats)
            
            # Update layer table (if method exists)
            if hasattr(self, 'update_layer_table'):
                layers = {}
                for p in self.paths:
                    l = p.get('layer', 'Unknown')
                    layers[l] = layers.get(l, 0) + 1
                self.update_layer_table(layers)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to parse SVG:\n{str(e)}")
            import traceback
            traceback.print_exc()
    
    def on_kerf_changed(self):
        """Update layer table when kerf changes"""
        if hasattr(self, 'update_layer_table_with_paths'):
            self.update_layer_table_with_paths()
        self.canvas.update()
    
    def parse_svg_path(self, d):
        """Parse SVG path data into points"""
        points = []
        current_x, current_y = 0, 0
        start_x, start_y = 0, 0
        
        # Split by commands, keeping the command letter
        import re
        commands = re.findall(r'[MmLlHhVvCcSsQqTtAaZz][^MmLlHhVvCcSsQqTtAaZz]*', d)
        
        for cmd_str in commands:
            cmd = cmd_str[0]
            params_str = cmd_str[1:].strip()
            
            if not params_str and cmd.upper() != 'Z':
                continue
            
            # Parse parameters
            try:
                params = [float(x) for x in re.findall(r'-?\d+\.?\d*', params_str)]
            except:
                params = []
            
            # M/m - Move to
            if cmd == 'M':
                if len(params) >= 2:
                    current_x, current_y = params[0], params[1]
                    start_x, start_y = current_x, current_y
                    points.append((current_x, current_y))
                    
                    # Additional coordinate pairs are treated as lineto
                    for i in range(2, len(params) - 1, 2):
                        current_x, current_y = params[i], params[i + 1]
                        points.append((current_x, current_y))
            
            elif cmd == 'm':
                if len(params) >= 2:
                    current_x += params[0]
                    current_y += params[1]
                    start_x, start_y = current_x, current_y
                    points.append((current_x, current_y))
                    
                    # Additional coordinate pairs are treated as lineto (relative)
                    for i in range(2, len(params) - 1, 2):
                        current_x += params[i]
                        current_y += params[i + 1]
                        points.append((current_x, current_y))
            
            # L/l - Line to
            elif cmd == 'L':
                for i in range(0, len(params) - 1, 2):
                    current_x, current_y = params[i], params[i + 1]
                    points.append((current_x, current_y))
            
            elif cmd == 'l':
                for i in range(0, len(params) - 1, 2):
                    current_x += params[i]
                    current_y += params[i + 1]
                    points.append((current_x, current_y))
            
            # H/h - Horizontal line
            elif cmd == 'H':
                for x in params:
                    current_x = x
                    points.append((current_x, current_y))
            
            elif cmd == 'h':
                for dx in params:
                    current_x += dx
                    points.append((current_x, current_y))
            
            # V/v - Vertical line
            elif cmd == 'V':
                for y in params:
                    current_y = y
                    points.append((current_x, current_y))
            
            elif cmd == 'v':
                for dy in params:
                    current_y += dy
                    points.append((current_x, current_y))
            
            # C/c - Cubic bezier (approximate with line segments)
            elif cmd == 'C':
                for i in range(0, len(params) - 5, 6):
                    # End point of curve
                    current_x, current_y = params[i + 4], params[i + 5]
                    points.append((current_x, current_y))
            
            elif cmd == 'c':
                for i in range(0, len(params) - 5, 6):
                    current_x += params[i + 4]
                    current_y += params[i + 5]
                    points.append((current_x, current_y))
            
            # S/s - Smooth cubic bezier
            elif cmd == 'S':
                for i in range(0, len(params) - 3, 4):
                    current_x, current_y = params[i + 2], params[i + 3]
                    points.append((current_x, current_y))
            
            elif cmd == 's':
                for i in range(0, len(params) - 3, 4):
                    current_x += params[i + 2]
                    current_y += params[i + 3]
                    points.append((current_x, current_y))
            
            # Q/q - Quadratic bezier
            elif cmd == 'Q':
                for i in range(0, len(params) - 3, 4):
                    current_x, current_y = params[i + 2], params[i + 3]
                    points.append((current_x, current_y))
            
            elif cmd == 'q':
                for i in range(0, len(params) - 3, 4):
                    current_x += params[i + 2]
                    current_y += params[i + 3]
                    points.append((current_x, current_y))
            
            # A/a - Arc (approximate with line)
            elif cmd == 'A':
                for i in range(0, len(params) - 6, 7):
                    current_x, current_y = params[i + 5], params[i + 6]
                    points.append((current_x, current_y))
            
            elif cmd == 'a':
                for i in range(0, len(params) - 6, 7):
                    current_x += params[i + 5]
                    current_y += params[i + 6]
                    points.append((current_x, current_y))
            
            # Z/z - Close path
            elif cmd.upper() == 'Z':
                if points and (points[0] != (current_x, current_y)):
                    points.append((start_x, start_y))
                    current_x, current_y = start_x, start_y
        
        return points
    
    def update_layer_table(self, layer_counts):
        """Update layer table with kerf type selection"""
        self.tbl_layers.setRowCount(len(layer_counts))
        
        row = 0
        for layer, count in sorted(layer_counts.items()):
            # Column 0: Layer name
            self.tbl_layers.setItem(row, 0, QTableWidgetItem(layer))
            
            # Column 1: Kerf Type dropdown
            kerf_combo = QComboBox()
            kerf_combo.addItems(['Outside Kerf', 'Inside Kerf', 'No Kerf'])
            
            # Auto-detect: holes get inside kerf, perimeters get outside kerf
            if 'hole' in layer.lower() or 'layer_2' in layer.lower():
                kerf_combo.setCurrentText('Inside Kerf')
            else:
                kerf_combo.setCurrentText('Outside Kerf')
            
            kerf_combo.currentTextChanged.connect(lambda: self.update_preview_colors())
            self.tbl_layers.setCellWidget(row, 1, kerf_combo)
            
            # Column 2: Count
            self.tbl_layers.setItem(row, 2, QTableWidgetItem(str(count)))
            
            # Column 3: Order
            self.tbl_layers.setItem(row, 3, QTableWidgetItem(str(row + 1)))
            
            row += 1
    
    def classify_path(self, path):
        """Determine kerf type for path - prioritize manually set type"""
        
        # FIRST: Check if kerf type was manually set (via right-click menu)
        if 'kerf_type' in path and path['kerf_type'] in ['inside', 'outside', 'none']:
            return path['kerf_type']
        
        # SECOND: Check layer table for kerf type
        layer = path.get('layer', '0')
        for row in range(self.tbl_layers.rowCount()):
            if self.tbl_layers.item(row, 0).text() == layer:
                combo = self.tbl_layers.cellWidget(row, 1)
                kerf_type = combo.currentText()
                
                if kerf_type == 'Inside Kerf':
                    return 'inside'
                elif kerf_type == 'Outside Kerf':
                    return 'outside'
                else:  # 'No Kerf'
                    return 'none'
        
        # THIRD: Default fallback - guess based on area
        if not path.get('closed', False):
            return 'none'
        
        # Use area to guess if not in table
        points = path['points']
        area = 0
        for i in range(len(points)):
            j = (i + 1) % len(points)
            area += points[i][0] * points[j][1]
            area -= points[j][0] * points[i][1]
        area = abs(area) / 2
        
        return 'inside' if area < 10000 else 'outside'
    
    def sort_toolpaths(self, toolpaths):
        """Sort toolpaths for optimal cutting order (inside-out)"""
        if not self.settings.get('enable_path_sorting', True):
            return toolpaths  # Return unsorted if disabled
        
        holes = []
        perimeters = []
        other = []
        
        # Separate paths by type
        for tp in toolpaths:
            kerf_type = tp.get('kerf_type', 'none')
            
            if kerf_type == 'inside':
                holes.append(tp)
            elif kerf_type == 'outside':
                perimeters.append(tp)
            else:
                other.append(tp)
        
        print(f"\n=== PATH SORTING ===")
        print(f"Found {len(holes)} holes, {len(perimeters)} perimeters, {len(other)} other paths")
        
        # Sort holes by size (smallest first) if enabled
        if self.settings.get('sort_by_size', True) and len(holes) > 0:
            def get_bounding_box_area(toolpath):
                points = toolpath['points']
                if len(points) < 2:
                    return 0
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                width = max(xs) - min(xs)
                height = max(ys) - min(ys)
                return width * height
            
            holes.sort(key=get_bounding_box_area)
            print(f"Sorted {len(holes)} holes by size (smallest first)")
        
        # Assemble final order
        if self.settings.get('sort_holes_first', True):
            sorted_paths = holes + other + perimeters
            print(f"Order: Holes ({len(holes)}) → Other ({len(other)}) → Perimeters ({len(perimeters)})")
        else:
            sorted_paths = toolpaths  # Keep original order
        
        print(f"=== SORTING COMPLETE ===\n")
        return sorted_paths    
    
    def rotate(self, vx, vy, angle_rad):
        ca = math.cos(angle_rad)
        sa = math.sin(angle_rad)
        return vx * ca - vy * sa, vx * sa + vy * ca
    
    def find_best_lead_position(self, points, kerf_type):
        """
        Select the corner with the largest interior angle.
        Fallback → longest straight edge.
        """
        
        if len(points) < 3:
            return None
        
        # Identify corners between 30° and 150°
        corners = self.find_corners(points, min_angle=30, max_angle=150)
        
        if not corners:
            return self.find_longest_edge_position(points, kerf_type)
        
        best_corner = None
        best_angle = -1.0
        min_edge_len = 0.5
        
        for c in corners:
            if c["angle"] <= best_angle:
                continue
            if min(c["prev_edge_len"], c["next_edge_len"]) < min_edge_len:
                continue
            best_corner = c
            best_angle = c["angle"]
        
        if best_corner is None:
            return self.find_longest_edge_position(points, kerf_type)
        
        return {
            "lead_point": best_corner["point"],
            "perp_direction": (0.0, 0.0),
            "start_index": best_corner["index"],
            "is_at_corner": True,
            "corner_info": best_corner,
        }
    
    def find_longest_edge_position(self, points, kerf_type):
        """Fallback for circular / rounded shapes."""
        
        if len(points) < 2:
            return None
        
        closed = (
            len(points) > 2
            and abs(points[0][0] - points[-1][0]) < 0.01
            and abs(points[0][1] - points[-1][1]) < 0.01
        )
        work_points = points[:-1] if closed else points
        
        longest_len = 0
        longest_idx = 0
        
        for i in range(len(work_points)):
            j = (i + 1) % len(work_points)
            dx = work_points[j][0] - work_points[i][0]
            dy = work_points[j][1] - work_points[i][1]
            L = math.hypot(dx, dy)
            if L > longest_len:
                longest_len = L
                longest_idx = i
        
        if longest_len < 1e-6:
            return None
        
        p1 = work_points[longest_idx]
        p2 = work_points[(longest_idx + 1) % len(work_points)]
        
        # 25% along the edge
        lead_point = (p1[0] + 0.25*(p2[0] - p1[0]), p1[1] + 0.25*(p2[1] - p1[1]))
        
        edge_dx = p2[0] - p1[0]
        edge_dy = p2[1] - p1[1]
        edge_len = math.hypot(edge_dx, edge_dy)
        
        perp_dx = -edge_dy / edge_len
        perp_dy =  edge_dx / edge_len
        
        # Direction test
        cx = sum(p[0] for p in work_points) / len(work_points)
        cy = sum(p[1] for p in work_points) / len(work_points)
        dot = perp_dx*(cx - lead_point[0]) + perp_dy*(cy - lead_point[1])
        
        if kerf_type == "inside" and dot < 0:
            perp_dx = -perp_dx
            perp_dy = -perp_dy
        elif kerf_type != "inside" and dot > 0:
            perp_dx = -perp_dx
            perp_dy = -perp_dy
        
        return {
            "lead_point": lead_point,
            "perp_direction": (perp_dx, perp_dy),
            "start_index": longest_idx,
            "is_at_corner": False,
            "corner_info": None,
        }
    
    def add_leads(self, points, is_hole, kerf_type='outside'):
        """Add angle-controlled lead-in / lead-out."""
        
        if kerf_type == 'none' or len(points) < 3:
            return points
        
        # Closed path check
        dx = abs(points[0][0] - points[-1][0])
        dy = abs(points[0][1] - points[-1][1])
        closed = (dx < 0.1 and dy < 0.1)
        if not closed:
            return points
        
        work_points = points[:-1]
        n = len(work_points)
        
        # Polygon center
        cx = sum(p[0] for p in work_points) / n
        cy = sum(p[1] for p in work_points) / n
        
        # Choose best lead location
        lead_info = self.find_best_lead_position(points, kerf_type)
        if not lead_info:
            return points
        
        lead_point = lead_info['lead_point']
        start_idx = lead_info['start_index']
        
        next_idx = (start_idx + 1) % n
        next_pt = work_points[next_idx]
        tx = next_pt[0] - lead_point[0]
        ty = next_pt[1] - lead_point[1]
        tlen = math.hypot(tx, ty)
        tx /= tlen
        ty /= tlen
        
        # Determine desired inward/outward direction
        v_to_center_x = cx - lead_point[0]
        v_to_center_y = cy - lead_point[1]
        target_sign = 1.0 if kerf_type == "outside" else -1.0
        
        result = []
        
        # ---------------------------
        # LEAD-IN
        # ---------------------------
        lead_in_len = self.settings.get('lead_in_len', 3.0)
        lead_in_angle = abs(self.settings.get('lead_in_angle', 30.0))
        
        if lead_in_len > 0:
            theta = math.radians(lead_in_angle)
            
            # Try both ± rotated tangents
            d1x, d1y = self.rotate(tx, ty, theta)
            d2x, d2y = self.rotate(tx, ty, -theta)
            
            dot1 = d1x*v_to_center_x + d1y*v_to_center_y
            dot2 = d2x*v_to_center_x + d2y*v_to_center_y
            
            score1 = target_sign * dot1
            score2 = target_sign * dot2
            
            if score1 >= score2:
                dx_in, dy_in = d1x, d1y
            else:
                dx_in, dy_in = d2x, d2y
            
            L = math.hypot(dx_in, dy_in)
            dx_in /= L
            dy_in /= L
            
            lead_in_pt = (lead_point[0] - dx_in*lead_in_len,
                          lead_point[1] - dy_in*lead_in_len)
            result.append(lead_in_pt)
        
        result.append(lead_point)
        
        # ---------------------------
        # CUT PATH
        # ---------------------------
        for i in range(n):
            idx = (next_idx + i) % n
            result.append(work_points[idx])
        
        result.append(lead_point)
        
        # ---------------------------
        # OVERCUT
        # ---------------------------
        overcut_len = self.settings.get('overcut_len', 0.0)
        if overcut_len > 0:
            oc_len = min(overcut_len, tlen*0.5)
            overcut_pt = (lead_point[0] + tx*oc_len,
                          lead_point[1] + ty*oc_len)
            result.append(overcut_pt)
        
        # ---------------------------
        # LEAD-OUT
        # ---------------------------
        lead_out_len = self.settings.get('lead_out_len', 3.0)
        lead_out_angle = abs(self.settings.get('lead_out_angle',
                                               self.settings.get('lead_in_angle', 30.0)))
        
        if lead_out_len > 0 and len(result) >= 2:
            end_pt = result[-1]
            prev_pt = result[-2]
            ex = end_pt[0] - prev_pt[0]
            ey = end_pt[1] - prev_pt[1]
            elen = math.hypot(ex, ey)
            ex /= elen
            ey /= elen
            
            th = math.radians(lead_out_angle)
            o1x, o1y = self.rotate(ex, ey, th)
            o2x, o2y = self.rotate(ex, ey, -th)
            
            v_end_x = cx - end_pt[0]
            v_end_y = cy - end_pt[1]
            
            dot_o1 = o1x*v_end_x + o1y*v_end_y
            dot_o2 = o2x*v_end_x + o2y*v_end_y
            
            if target_sign*dot_o1 >= target_sign*dot_o2:
                dx_out, dy_out = o1x, o1y
            else:
                dx_out, dy_out = o2x, o2y
            
            L = math.hypot(dx_out, dy_out)
            dx_out /= L
            dy_out /= L
            
            lead_out_pt = (end_pt[0] + dx_out*lead_out_len,
                           end_pt[1] + dy_out*lead_out_len)
            result.append(lead_out_pt)
        
        return result
    
    def find_corners(self, points, min_angle=30, max_angle=150):
            """Find all corners in the path with their angles"""
            corners = []
            
            if len(points) < 3:
                return corners
            
            # Remove duplicate last point if closed
            work_points = points[:-1] if (len(points) > 2 and 
                                          abs(points[0][0] - points[-1][0]) < 0.01 and
                                          abs(points[0][1] - points[-1][1]) < 0.01) else points
            
            for i in range(len(work_points)):
                prev_idx = (i - 1) % len(work_points)
                next_idx = (i + 1) % len(work_points)
                
                p1 = work_points[prev_idx]
                p2 = work_points[i]  # Corner point
                p3 = work_points[next_idx]
                
                # Vector from p1 to p2
                v1x = p2[0] - p1[0]
                v1y = p2[1] - p1[1]
                len1 = math.sqrt(v1x*v1x + v1y*v1y)
                
                # Vector from p2 to p3
                v2x = p3[0] - p2[0]
                v2y = p3[1] - p2[1]
                len2 = math.sqrt(v2x*v2x + v2y*v2y)
                
                if len1 < 0.001 or len2 < 0.001:
                    continue
                
                # Normalize vectors
                v1x /= len1
                v1y /= len1
                v2x /= len2
                v2y /= len2
                
                # Calculate angle
                dot = v1x * v2x + v1y * v2y
                dot = max(-1.0, min(1.0, dot))  # Clamp for numerical stability
                angle = math.degrees(math.acos(dot))
                
                # Determine if inside or outside corner using cross product
                cross = v1x * v2y - v1y * v2x
                is_inside = cross < 0  # Negative cross product = inside corner (concave)
                
                # Only consider significant corners
                if angle >= min_angle and angle <= max_angle:
                    corners.append({
                        'index': i,
                        'point': p2,
                        'angle': angle,
                        'is_inside': is_inside,
                        'prev_edge_len': len1,
                        'next_edge_len': len2
                    })
            
            return corners
    
    def find_longest_edge_position(self, points, kerf_type):
        """Fallback method to find lead position on longest edge"""
        if len(points) < 2:
            return None
        
        # Find longest edge
        work_points = points[:-1] if (len(points) > 2 and 
                                      abs(points[0][0] - points[-1][0]) < 0.01 and
                                      abs(points[0][1] - points[-1][1]) < 0.01) else points
        
        longest_idx = 0
        longest_len = 0
        
        for i in range(len(work_points)):
            next_i = (i + 1) % len(work_points)
            dx = work_points[next_i][0] - work_points[i][0]
            dy = work_points[next_i][1] - work_points[i][1]
            edge_len = math.sqrt(dx*dx + dy*dy)
            
            if edge_len > longest_len:
                longest_len = edge_len
                longest_idx = i
        
        if longest_len < 0.001:
            return None
        
        # Get edge points
        start_pt = work_points[longest_idx]
        end_pt = work_points[(longest_idx + 1) % len(work_points)]
        
        # Position at 25% along edge
        t = 0.25
        lead_point = (
            start_pt[0] + t * (end_pt[0] - start_pt[0]),
            start_pt[1] + t * (end_pt[1] - start_pt[1])
        )
        
        # Calculate perpendicular
        edge_dx = end_pt[0] - start_pt[0]
        edge_dy = end_pt[1] - start_pt[1]
        edge_len = math.sqrt(edge_dx*edge_dx + edge_dy*edge_dy)
        
        if edge_len < 0.001:
            return None
        
        perp_dx = -edge_dy / edge_len
        perp_dy = edge_dx / edge_len
        
        # Determine direction based on shape center
        center_x = sum(p[0] for p in work_points) / len(work_points)
        center_y = sum(p[1] for p in work_points) / len(work_points)
        
        to_center_x = center_x - lead_point[0]
        to_center_y = center_y - lead_point[1]
        dot = perp_dx * to_center_x + perp_dy * to_center_y
        
        if kerf_type == 'inside':
            if dot < 0:
                perp_dx = -perp_dx
                perp_dy = -perp_dy
        else:  # outside or none
            if dot > 0:
                perp_dx = -perp_dx
                perp_dy = -perp_dy
        
        return {
            'lead_point': lead_point,
            'perp_direction': (perp_dx, perp_dy),
            'start_index': longest_idx,
            'is_at_corner': False,
            'corner_info': None
        }
    
    def generate_toolpaths(self):
        print("=" * 50)
        print("DEBUG: generate_toolpaths() CALLED!")
        print(f"DEBUG: Number of paths: {len(self.paths)}")
        print("=" * 50)
        
        self.toolpaths = []
        
        for idx, path in enumerate(self.paths):
            print(f"\nDEBUG: Checking path {idx}")
            
            if 'kerf_type' in path:
                print(f"  - kerf_type value: '{path['kerf_type']}'")
            
            # SKIP UNSELECTED PATHS
            if 'kerf_type' not in path or path['kerf_type'] not in ['inside', 'outside', 'none']:
                print(f"  - ❌ SKIPPING (no kerf_type or invalid)")
                continue
            
            print(f"  - ✅ PROCESSING THIS PATH!")
            
            points = path.get('points', [])
            
            if len(points) < 2:
                print(f"  - ❌ SKIPPING (not enough points)")
                continue
            
            # Optional per-path scaling (size adjustment)
            scale_factor = path.get('scale', 1.0)
            if abs(scale_factor - 1.0) > 1e-6:
                scaled_points = [(p[0] * scale_factor, p[1] * scale_factor) for p in points]
            else:
                scaled_points = points
            
            kerf_type = path.get('kerf_type', 'outside')
            
            # Step 1: Apply kerf offset if needed
            if kerf_type != 'none' and self.settings['apply_kerf']:
                try:
                    offset_points = self.apply_kerf(scaled_points, kerf_type)
                    print(f"  - Applied kerf offset: {len(offset_points)} points")
                except Exception as e:
                    print(f"  - ❌ ERROR in apply_kerf: {e}")
                    offset_points = scaled_points[:]
            else:
                offset_points = scaled_points[:]
                print(f"  - No kerf offset applied")
            
            # Step 2: Add leads ONLY if kerf type is not 'none' and leads are enabled
            leads_enabled = path.get('leads_enabled', True)
            if kerf_type != 'none' and leads_enabled:
                print(f"  - Adding leads for {kerf_type} kerf (leads enabled)...")
                is_hole = (kerf_type == 'inside')
                try:
                    final_points = self.add_leads(offset_points, is_hole, kerf_type)
                    print(f"  - Leads added: {len(final_points)} points")
                except Exception as e:
                    print(f"  - ❌ ERROR in add_leads: {e}")
                    final_points = offset_points[:]
            else:
                # NO LEADS (either kerf type is 'none' or leads disabled)
                reason = "kerf type is 'none'" if kerf_type == 'none' else "leads disabled for this path"
                print(f"  - NO LEADS ADDED ({reason})")
                final_points = offset_points[:]
            
            # Step 3: Create toolpath
            print(f"  - Creating toolpath...")
            self.toolpaths.append({
                'points': final_points,
                'kerf_type': kerf_type,
                'is_hole': (kerf_type == 'inside'),
                'layer': path.get('layer', '0'),
                'closed': path.get('closed', False),
                'feed': path.get('feed', None),
                'scale': path.get('scale', 1.0),
                'leads_enabled': path.get('leads_enabled', True),
            })
            print(f"  - ✅ Path {idx} COMPLETED with {len(final_points)} points!")
        
        print("\n" + "=" * 50)
        print(f"TOTAL TOOLPATHS GENERATED: {len(self.toolpaths)}")
        
        # Sort toolpaths for optimal cutting order
        self.toolpaths = self.sort_toolpaths(self.toolpaths)
        print(f"Toolpaths sorted: {len(self.toolpaths)} paths in optimized order")
        print("=" * 50)
        
        # Update canvas
        self.canvas.set_paths(self.toolpaths)
        
        # Show summary
        outside = sum(1 for p in self.toolpaths if p.get('kerf_type') == 'outside')
        inside = sum(1 for p in self.toolpaths if p.get('kerf_type') == 'inside')
        none = sum(1 for p in self.toolpaths if p.get('kerf_type') == 'none')
        
        QMessageBox.information(self, "Success", 
            f"Generated {len(self.toolpaths)} toolpaths\n"
            f"🔴 Outside Kerf: {outside}\n"
            f"🔵 Inside Kerf: {inside}\n"
            f"🟢 No Kerf: {none}")    
    
    def apply_kerf(self, points, kerf_type):
        """Apply kerf offset based on type"""
        if kerf_type == 'none':
            return points  # No offset
        
        offset = self.settings['kerf'] / 2
        
        if kerf_type == 'inside':
            offset = -offset  # Negative offset (shrink)
        
        # Check if input is closed
        is_closed = False
        if len(points) > 2:
            dx = abs(points[0][0] - points[-1][0])
            dy = abs(points[0][1] - points[-1][1])
            is_closed = (dx < 0.01 and dy < 0.01)
        
        # Work with unique points (remove duplicate closing point if present)
        work_points = points[:-1] if is_closed else points[:]
        
        result = []
        n = len(work_points)
        
        for i in range(n):
            prev_idx = (i - 1) % n
            next_idx = (i + 1) % n
            
            p1 = work_points[prev_idx]
            p2 = work_points[i]
            p3 = work_points[next_idx]
            
            dx1 = p2[0] - p1[0]
            dy1 = p2[1] - p1[1]
            len1 = math.sqrt(dx1*dx1 + dy1*dy1) or 1
            n1x = -dy1 / len1
            n1y = dx1 / len1
            
            dx2 = p3[0] - p2[0]
            dy2 = p3[1] - p2[1]
            len2 = math.sqrt(dx2*dx2 + dy2*dy2) or 1
            n2x = -dy2 / len2
            n2y = dx2 / len2
            
            nx = (n1x + n2x) / 2
            ny = (n1y + n2y) / 2
            nlen = math.sqrt(nx*nx + ny*ny) or 1
            nx /= nlen
            ny /= nlen
            
            new_x = p2[0] + nx * offset
            new_y = p2[1] + ny * offset
            result.append((new_x, new_y))
        
        # CRITICAL: If original was closed, close the result too!
        if is_closed and len(result) > 0:
            # Add closing point
            result.append(result[0])
        
        return result
    
    def is_corner_point(self, points, idx, threshold_angle):
        """Detect if point is a corner based on angle change"""
        if idx <= 0 or idx >= len(points) - 1:
            return False
        
        p1 = points[idx - 1]
        p2 = points[idx]
        p3 = points[idx + 1]
        
        # Calculate segment vectors
        v1x = p2[0] - p1[0]
        v1y = p2[1] - p1[1]
        v2x = p3[0] - p2[0]
        v2y = p3[1] - p2[1]
        
        # Calculate segment lengths
        len1 = math.sqrt(v1x*v1x + v1y*v1y)
        len2 = math.sqrt(v2x*v2x + v2y*v2y)
        
        # Ignore tiny segments (< 1mm) - likely noise
        if len1 < 1.0 or len2 < 1.0:
            return False
        
        # Normalize vectors
        v1x /= len1
        v1y /= len1
        v2x /= len2
        v2y /= len2
        
        # Calculate dot product
        dot = v1x * v2x + v1y * v2y
        dot = max(-1.0, min(1.0, dot))  # Clamp for numerical stability
        
        # Calculate angle between segments
        angle = math.degrees(math.acos(dot))
        
        # Detect SHARP corners (angle deviation from 180°)
        # A straight line = 180°, sharp corner = low angle
        deviation = 180.0 - angle
        
        # Return True if deviation is GREATER than threshold
        # threshold_angle = 45 means: detect corners sharper than 135° (180-45)
        return deviation >= threshold_angle
    
    def generate_gcode(self):
        if not self.toolpaths:
            QMessageBox.warning(self, "No Toolpaths", "Generate toolpaths first")
            return
        
        self.update_settings_from_ui()
        post = POST_PROCESSORS[self.settings['post']]
        gcode = []
        
        # Coolant M-codes
        coolant_mode = self.settings.get('coolant_mode', 'off')
        self.settings['coolant_start'] = 'M7 ; Mist ON' if coolant_mode == 'mist' else ('M8 ; Flood ON' if coolant_mode == 'flood' else '')
        self.settings['coolant_stop'] = 'M9 ; Coolant OFF' if coolant_mode in ['mist', 'flood'] else ''
        
        # Initial Header
        header = post['header'].format(**self.settings)
        gcode.extend(header.strip().split('\n'))
        
        # Global Touch-Off (Once per job)
        if self.settings['touch_off'] and self.settings['touch_mode'] == 'once_job':
            touch = post.get('touch_off', '').format(**self.settings)
            if touch:
                gcode.extend(touch.strip().split('\n'))
        
        # --- CHAIN CUTTING AND PATH LOOP SETUP ---
        chain_cutting_enabled = self.settings.get('chain_cutting', False)
        chain_distance = self.settings.get('chain_distance', 50.0)
        last_cut_end_point = None # (x, y) coordinates of the previous path's end point
        
        for idx, toolpath in enumerate(self.toolpaths):
            points = toolpath['points']
            is_hole = toolpath['is_hole']
            kerf_type = toolpath.get('kerf_type', 'outside')
            
            if len(points) < 2:
                continue
            
            start_x, start_y = points[0][0], points[0][1]
            end_x, end_y = points[-1][0], points[-1][1]
            
            # --- END SEQUENCE OF PREVIOUS PATH / START SEQUENCE OF NEW PATH ---
            
            should_chain = False
            
            # 1. Check if chaining is active and possible
            if chain_cutting_enabled and last_cut_end_point:
                dx = start_x - last_cut_end_point[0]
                dy = start_y - last_cut_end_point[1]
                dist = math.sqrt(dx*dx + dy*dy)
                
                if dist <= chain_distance:
                    should_chain = True
            
            if should_chain:
                # === CHAIN CUT CONTINUITY ===
                gcode.append(f"\n; Path {idx+1} (CHAINED) - Kerf: {kerf_type}")
                gcode.append(f"; Distance: {dist:.1f} mm. Skipping retract/re-pierce.")
                
                # Rapid move at cut height to the next pierce point
                gcode.append(f"G0 Z{self.settings['cut_height']:.3f}")
                gcode.append(f"G0 X{start_x + self.settings['offset_x']:.3f} Y{start_y + self.settings['offset_y']:.3f}")
                
                # Arc must be off from the previous path, so turn it on.
                # Use a small delay for arc stabilization, then start cutting.
                gcode.append("M3 S{power}".format(**self.settings))
                gcode.append("G4 P0.1 ; Stabilize arc for chain cut")
                gcode.append("G1 Z{cut_height} F500 ; Re-engage cutting height")
                
            else:
                # === STANDARD START SEQUENCE ===
                
                # If not the first path, close the previous one (retract/arc off)
                if idx > 0:
                    end_code = post.get('end', '').format(**self.settings)
                    if end_code:
                        gcode.extend(end_code.strip().split('\n'))
                
                gcode.append(f"\n; Path {idx+1} (STANDARD) - Kerf: {kerf_type}")
                
                # Rapid move to start point (at safe Z)
                gcode.append(f"G0 X{start_x + self.settings['offset_x']:.3f} Y{start_y + self.settings['offset_y']:.3f}")
                
                # Touch-Off (Per cut / Holes only)
                if self.settings['touch_off'] and (self.settings['touch_mode'] == 'per_cut' or (self.settings['touch_mode'] == 'holes_only' and is_hole)):
                    touch = post.get('touch_off', '').format(**self.settings)
                    if touch:
                        gcode.extend(touch.strip().split('\n'))
                
                # Pierce Sequence
                pierce = post.get('pierce', '').format(**self.settings)
                if pierce:
                    gcode.extend(pierce.strip().split('\n'))
            
            # --- CUTTING MOVES ---
            
            feed = toolpath.get('feed', self.settings['feed'])
            
            # Small hole feed rate adjustment
            if is_hole:
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                width = max(xs) - min(xs)
                height = max(ys) - min(ys)
                diameter = (width + height) / 2
                
                if diameter <= self.settings['small_hole_threshold']:
                    feed = int(feed * self.settings['small_hole_feed_percent'] / 100)
                    gcode.append(f"; Small hole detected (Ø{diameter:.1f}mm), feed reduced to {feed}")
            
            # THC logic for corner slowing/disabling
            thc_enabled = self.settings.get('thc_enable', False)
            thc_at_corners = self.settings.get('thc_disable_corners', True)
            corner_angle = self.settings.get('thc_corner_angle', 90)
            
            thc_is_on = thc_enabled and not should_chain # Assume THC is ON unless chained
            
            if thc_enabled and not should_chain:
                # Only need to turn on M67 E0 Q100 if we did a full pierce cycle
                gcode.append("M67 E0 Q100  ; THC ON (start of path)")
                
            corners = set()
            if thc_enabled and thc_at_corners:
                for i in range(1, len(points) - 1):
                    if self.is_corner_point(points, i, corner_angle):
                        corners.add(i)
            
            # Cut from the lead-in point (index 0) to the end
            for i, pt in enumerate(points[1:], 1):
                
                # Corner THC disable logic
                if thc_enabled and thc_at_corners and thc_is_on and i in corners:
                    # Logic is simple: disable THC at the start of the corner move
                    gcode.append("M68 E0 Q0    ; THC OFF (corner)")
                    thc_is_on = False
                
                gcode.append(post['cut'].format(
                    x=pt[0] + self.settings['offset_x'], 
                    y=pt[1] + self.settings['offset_y'], 
                    feed=feed
                ))
                
                # Corner THC re-enable logic
                if thc_enabled and thc_at_corners and not thc_is_on and i not in corners:
                    # If the move is long enough and we are past the corner, re-enable
                    # Simple re-enable: if the next point is NOT a corner, turn THC back on
                    gcode.append("M67 E0 Q100  ; THC ON (after corner)")
                    thc_is_on = True
            
            # Ensure THC is off at the end of the cut
            if thc_enabled:
                gcode.append("M68 E0 Q0    ; THC OFF (end of path)")
            
            # Update the last cut point for the next path's chain check
            last_cut_end_point = (end_x, end_y)
            
        # --- FINAL FOOTER ---
        
        # Always close out the last path with a full retract (M5/G0 Z_safe)
        end_code = post.get('end', '').format(**self.settings)
        if end_code:
            gcode.extend(end_code.strip().split('\n'))
            
        # Final M2/M30/etc.
        footer = post.get('footer', '').format(**self.settings)
        if footer:
            gcode.extend(footer.strip().split('\n'))
        
        self.gcode_lines = gcode
        self.txt_gcode.setText('\n'.join(gcode))
        
        cut_length = 0
        for toolpath in self.toolpaths:
            points = toolpath['points']
            for i in range(len(points) - 1):
                dx = points[i+1][0] - points[i][0]
                dy = points[i+1][1] - points[i][1]
                cut_length += math.sqrt(dx*dx + dy*dy)
        
        cut_time = cut_length / self.settings['feed'] * 60
        
        QMessageBox.information(self, "G-code Generated",
            f"Lines: {len(gcode)}\n"
            f"Paths: {len(self.toolpaths)}\n"
            f"Cut Length: {cut_length:.1f} mm\n"
            f"Est. Cut Time: {cut_time:.1f} min\n"
            f"Post-Processor: {post['name']}")
    
    def save_gcode(self):
        if not self.gcode_lines:
            QMessageBox.warning(self, "No G-code", "Generate G-code first")
            return
        
        post = POST_PROCESSORS[self.settings['post']]
        ext = post['ext']
        
        default_name = Path(self.filename).stem + ext if self.filename else f"output{ext}"
        
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save G-code", default_name,
            f"G-code Files (*{ext});;All Files (*)"
        )
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write('\n'.join(self.gcode_lines))
                QMessageBox.information(self, "Success", f"G-code saved to:\n{filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error saving file:\n{str(e)}")

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    app.setStyleSheet("""
        QMainWindow, QWidget {
            background-color: #1a1a1a;
            color: #e0e0e0;
        }
        QGroupBox {
            border: 1px solid #444;
            border-radius: 5px;
            margin-top: 10px;
            padding-top: 10px;
            font-weight: bold;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
        }
        QPushButton {
            background-color: #2563eb;
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #1d4ed8;
        }
        QComboBox, QSpinBox, QDoubleSpinBox {
            background-color: #2a2a2a;
            border: 1px solid #444;
            border-radius: 3px;
            padding: 3px;
        }
        QTextEdit {
            background-color: #0a0a0a;
            border: 1px solid #444;
        }
        QTableWidget {
            background-color: #2a2a2a;
            gridline-color: #444;
        }
        QTabWidget::pane {
            border: 1px solid #444;
        }
        QTabBar::tab {
            background-color: #2a2a2a;
            border: 1px solid #444;
            padding: 6px 12px;
        }
        QTabBar::tab:selected {
            background-color: #3a3a3a;
        }
    """)
    
    window = FireBridgeCAM()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()