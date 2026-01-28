from __future__ import annotations

import numpy as np


def draw_outline(edge_mask: np.ndarray, width: int, intensity: float) -> np.ndarray:
    width = max(1, int(round(width)))
    alpha = np.clip(float(intensity), 0.0, 1.0)
    h, w = edge_mask.shape
    out = np.zeros((h, w, 4), dtype=np.float32)
    if edge_mask.max() <= 0:
        return out
    # simple dilation-based outline
    dil = edge_mask.copy()
    for _ in range(width - 1):
        dil = np.maximum.reduce([
            dil,
            np.pad(dil, ((0, 0), (1, 0)), constant_values=0)[:, :-1],
            np.pad(dil, ((0, 0), (0, 1)), constant_values=0)[:, 1:],
            np.pad(dil, ((1, 0), (0, 0)), constant_values=0)[1:, :],
            np.pad(dil, ((0, 1), (0, 0)), constant_values=0)[:-1, :],
        ])
    out[..., 0:3] = 1.0  # white
    out[..., 3] = np.clip(dil * alpha, 0.0, 1.0)
    return out


def draw_rays(edge_mask: np.ndarray, dist_field: np.ndarray, count: int, max_length: float, spread_deg: float, audio_levels: np.ndarray) -> np.ndarray:
    h, w = edge_mask.shape
    out = np.zeros((h, w, 4), dtype=np.float32)
    if edge_mask.max() <= 0 or count <= 0:
        return out
    
    # Sample contour points (every ~8-12px)
    step = max(1, int(8 + 4 * (1.0 - audio_levels[2] if len(audio_levels) > 2 else 0.5)))
    points = []
    for y in range(0, h, step):
        for x in range(0, w, step):
            if edge_mask[y, x] > 0.5:
                points.append((x, y))
    
    if len(points) == 0:
        return out
    
    # Limit points by quality setting
    max_points = min(count, len(points))
    if len(points) > max_points:
        indices = np.linspace(0, len(points)-1, max_points, dtype=int)
        points = [points[i] for i in indices]
    
    # Audio-driven parameters
    base_length = max_length * (0.3 + 0.7 * (audio_levels[0] if len(audio_levels) > 0 else 0.5))  # 60Hz
    beat_kick = audio_levels[1] if len(audio_levels) > 1 else 0.5  # 150Hz
    shimmer = audio_levels[4] if len(audio_levels) > 4 else 0.5  # 2.4kHz
    motion_budget = np.mean(audio_levels) if len(audio_levels) > 0 else 0.5
    
    # Draw rays from each point
    for px, py in points:
        # Estimate normal from gradient
        gx = 0.0
        gy = 0.0
        if px > 0 and px < w-1 and py > 0 and py < h-1:
            gx = edge_mask[py, px+1] - edge_mask[py, px-1]
            gy = edge_mask[py+1, px] - edge_mask[py-1, px]
        
        if abs(gx) < 0.1 and abs(gy) < 0.1:
            # Fallback: random direction
            angle = np.random.uniform(0, 2*np.pi)
        else:
            angle = np.arctan2(gy, gx) + np.pi/2  # Perpendicular to gradient
        
        # Ray count and spread
        ray_count = max(1, int(3 + 5 * shimmer))
        spread_rad = np.radians(spread_deg)
        
        for i in range(ray_count):
            ray_angle = angle + np.random.uniform(-spread_rad/2, spread_rad/2)
            
            # Length with beat kick and motion budget
            length = base_length * (1.0 + 0.8 * beat_kick) * (0.5 + 1.0 * motion_budget)
            length = max(5, min(length, max_length * 2))
            
            # Draw ray line
            dx = np.cos(ray_angle)
            dy = np.sin(ray_angle)
            
            for t in range(int(length)):
                x = int(px + t * dx)
                y = int(py + t * dy)
                if 0 <= x < w and 0 <= y < h:
                    # Fade out towards end
                    alpha = (1.0 - t/length) * motion_budget * 0.8
                    out[y, x, 0:3] = 1.0  # White
                    out[y, x, 3] = max(out[y, x, 3], alpha)
    
    return out


def draw_bands(dist_field: np.ndarray, step_px: int, thickness: int, speed: float, audio_levels: np.ndarray) -> np.ndarray:
    h, w = dist_field.shape
    out = np.zeros((h, w, 4), dtype=np.float32)
    if dist_field.max() <= 0:
        return out
    
    # Audio-driven breathing and shimmer
    breathing = audio_levels[0] if len(audio_levels) > 0 else 0.5  # 60Hz
    shimmer = audio_levels[4] if len(audio_levels) > 4 else 0.5  # 2.4kHz
    motion_budget = np.mean(audio_levels) if len(audio_levels) > 0 else 0.5
    
    # Create equidistant bands
    max_dist = dist_field.max()
    band_count = int(max_dist / step_px)
    
    for i in range(band_count):
        # Phase shift based on audio
        phase = i * 0.3 + speed * 0.1 + shimmer * 0.2
        breathing_amp = 1.0 + 0.4 * breathing * motion_budget
        center_dist = (i + 0.5) * step_px * breathing_amp
        
        # Create band mask
        band_mask = np.abs(dist_field - center_dist) <= thickness/2
        
        # Shimmer effect
        if shimmer > 0.3:
            jitter = np.random.normal(0, 0.5, (h, w))
            band_mask = band_mask & (np.abs(dist_field - center_dist + jitter) <= thickness/2)
        
        # Apply to output
        alpha = 0.6 * motion_budget * (1.0 - i/band_count)
        out[band_mask, 0:3] = 1.0  # White
        out[band_mask, 3] = np.maximum(out[band_mask, 3], alpha)
    
    return out


def draw_sparkles(edge_mask: np.ndarray, density: float, speed: float, audio_levels: np.ndarray) -> np.ndarray:
    h, w = edge_mask.shape
    out = np.zeros((h, w, 4), dtype=np.float32)
    if edge_mask.max() <= 0 or density <= 0:
        return out
    
    # Audio-driven parameters
    high_freq = audio_levels[4] if len(audio_levels) > 4 else 0.5  # 2.4kHz
    motion_budget = np.mean(audio_levels) if len(audio_levels) > 0 else 0.5
    
    # Only show sparkles when high frequencies are active
    if high_freq < 0.2:
        return out
    
    # Sample edge points for sparkles
    edge_points = []
    step = max(1, int(4 / density))  # More points for higher density
    for y in range(0, h, step):
        for x in range(0, w, step):
            if edge_mask[y, x] > 0.5:
                edge_points.append((x, y))
    
    if len(edge_points) == 0:
        return out
    
    # Limit sparkle count
    max_sparkles = min(int(density * 50), len(edge_points))
    if len(edge_points) > max_sparkles:
        indices = np.random.choice(len(edge_points), max_sparkles, replace=False)
        edge_points = [edge_points[i] for i in indices]
    
    # Draw sparkles
    for px, py in edge_points:
        # Sparkle size and intensity based on audio
        size = int(1 + 2 * high_freq * motion_budget)
        intensity = high_freq * motion_budget * 0.8
        
        # Add some randomness
        if np.random.random() < 0.3:  # 30% chance per frame
            # Draw small bright dot
            for dy in range(-size, size+1):
                for dx in range(-size, size+1):
                    x, y = px + dx, py + dy
                    if 0 <= x < w and 0 <= y < h:
                        dist = np.sqrt(dx*dx + dy*dy)
                        if dist <= size:
                            alpha = intensity * (1.0 - dist/size)
                            out[y, x, 0:3] = 1.0  # White
                            out[y, x, 3] = max(out[y, x, 3], alpha)
    
    return out


def compose(base_rgb: np.ndarray, overlay_rgba: np.ndarray, alpha: float = 1.0) -> np.ndarray:
    base = base_rgb.astype(np.float32) / 255.0
    ov = overlay_rgba.astype(np.float32)
    a = np.clip(ov[..., 3:4] * float(alpha), 0.0, 1.0)
    rgb = ov[..., 0:3]
    out = base * (1 - a) + rgb * a
    out = np.clip(out * 255.0, 0, 255).astype(np.uint8)
    return out


