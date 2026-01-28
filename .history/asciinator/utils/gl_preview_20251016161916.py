import numpy as np

try:
    from PyQt5.QtWidgets import QOpenGLWidget
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QSurfaceFormat
except Exception:
    from PyQt6.QtWidgets import QOpenGLWidget
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QSurfaceFormat

from OpenGL.GL import (
    glClearColor, glClear, GL_COLOR_BUFFER_BIT,
    glViewport,
    glGenTextures, glBindTexture, glTexParameteri,
    glTexImage2D, GL_TEXTURE_2D, GL_RED, GL_UNSIGNED_BYTE,
    GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER, GL_NEAREST,
    glUseProgram, glGetUniformLocation, glUniform1i, glUniform2f, glUniform1f,
    glGenVertexArrays, glBindVertexArray, glGenBuffers, glBindBuffer,
    glBufferData, GL_ARRAY_BUFFER, GL_STATIC_DRAW,
    glEnableVertexAttribArray, glVertexAttribPointer,
    glDrawArrays, GL_TRIANGLES
)
from OpenGL.GL.shaders import compileProgram, compileShader


VERT_SHADER = """
#version 330 core
layout (location = 0) in vec2 aPos;
layout (location = 1) in vec2 aUV;
out vec2 vUV;
void main() {
    vUV = aUV;
    gl_Position = vec4(aPos, 0.0, 1.0);
}
"""

FRAG_SHADER = """
#version 330 core
in vec2 vUV;
out vec4 FragColor;
uniform sampler2D uTex;       // grayscale grid [0..1]
uniform sampler2D uEdges;     // edges mask [0..1]
uniform sampler2D uDist;      // distance field in pixels (normalized or absolute)
uniform vec2 uTexSize;        // width, height in texels

// Toggles (0/1)
uniform int uEnableOutline;
uniform int uEnableRays;
uniform int uEnableEcho;
uniform int uEnableSparkles;
uniform int uEnableBackground;

// Audio bands
uniform float uBands[6];
uniform float uTime;

// Params
uniform float uRaysLength;
uniform float uRaysIntensity;
uniform float uEchoSpacing;
uniform float uEchoBand;
uniform int   uEchoLines;
uniform float uSparklesDensity;
uniform float uSparklesGain;
uniform float uBgIntensity;
uniform float uBgSpeed;

// Hash noise from UV for sparkles
float hash21(vec2 p){
    p = fract(p*vec2(123.34, 345.45));
    p += dot(p, p+34.345);
    return fract(p.x*p.y);
}

void main() {
    float g = texture(uTex, vUV).r; // base grayscale
    vec2 uv = vUV;
    vec2 texel = 1.0 / uTexSize;
    float overlay = 1.0;

    // Sample edges/dist (nearest is fine)
    float edge = texture(uEdges, uv).r;
    float dist = texture(uDist, uv).r; // assume pixels or scaled

    if(uEnableOutline == 1){
        float lvl = 0.6*uBands[1] + 0.4*uBands[2];
        if(lvl > 0.01){
            overlay *= (1.0 + 3.0*lvl*step(0.5, edge));
        }
    }

    if(uEnableRays == 1){
        float lvl = 0.4*uBands[0] + 0.4*uBands[1] + 0.2*uBands[4];
        if(lvl > 0.01){
            float s = max(1.0, 0.3*uRaysLength);
            float gain = uRaysIntensity * lvl * exp(-dist / s);
            overlay *= (1.0 + gain);
        }
    }

    if(uEnableEcho == 1){
        float level = 0.3*uBands[2] + 0.7*uBands[3];
        if(level > 0.005 && uEchoSpacing > 0.0 && uEchoLines > 0){
            // Create band around multiples of spacing
            float b = 0.0;
            float spacing = uEchoSpacing;
            float halfw = 0.5*uEchoBand;
            // approximate periodic bands using distance to nearest multiple
            float m = floor((dist/spacing) + 0.5);
            float d2m = abs(dist - m*spacing);
            float band = smoothstep(halfw, 0.0, d2m);
            b = band;
            overlay *= (1.0 + 0.5*level*b);
        }
    }

    if(uEnableSparkles == 1){
        float lvl = 0.5*uBands[4] + 0.5*uBands[5];
        if(lvl > 0.01){
            float density = uSparklesDensity * (0.2 + 0.8*lvl);
            float rnd = hash21(uv * uTexSize);
            float s = step(1.0 - density, rnd) * step(0.5, edge); // only on edges
            overlay *= (1.0 + uSparklesGain * lvl * s);
        }
    }

    if(uEnableBackground == 1){
        float lvl = 0.6*uBands[0] + 0.4*uBands[1];
        float wave = sin(0.02*uv.x*uTexSize.x + 0.02*uv.y*uTexSize.y + uTime*uBgSpeed);
        overlay *= (1.0 + uBgIntensity * lvl * (0.5 + 0.5*wave));
    }

    float outv = clamp(g * overlay, 0.0, 1.0);
    FragColor = vec4(outv, outv, outv, 1.0);
}
"""


class GLPreviewWidget(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(0)
        fmt.setStencilBufferSize(0)
        self.setFormat(fmt)
        self._program = None
        self._vao = None
        self._vbo = None
        self._tex = None
        self._tex_edges = None
        self._tex_dist = None
        self._grid_tex_size = (1, 1)
        self._pending_grid = None  # numpy 2D uint8 or float [0..1]
        self._pending_edges = None
        self._pending_dist = None
        self._bands = np.zeros(6, dtype=np.float32)
        self._toggles = {
            'outline': 0, 'rays': 0, 'echo': 0, 'sparkles': 0, 'bg': 0
        }
        self._params = {
            'raysLength': 80.0, 'raysIntensity': 1.0,
            'echoSpacing': 10.0, 'echoBand': 3.0, 'echoLines': 4,
            'sparklesDensity': 0.3, 'sparklesGain': 3.0,
            'bgIntensity': 0.5, 'bgSpeed': 1.0
        }
        self._time = 0.0
        self.setMinimumSize(200, 150)

    def initializeGL(self):
        glClearColor(0.0, 0.0, 0.0, 1.0)
        # Quad covering screen
        verts = np.array([
            -1.0, -1.0,  0.0, 0.0,
             1.0, -1.0,  1.0, 0.0,
             1.0,  1.0,  1.0, 1.0,
            -1.0, -1.0,  0.0, 0.0,
             1.0,  1.0,  1.0, 1.0,
            -1.0,  1.0,  0.0, 1.0,
        ], dtype=np.float32)
        self._vao = glGenVertexArrays(1)
        glBindVertexArray(self._vao)
        self._vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo)
        glBufferData(GL_ARRAY_BUFFER, verts.nbytes, verts, GL_STATIC_DRAW)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 2, 0x1406, False, 16, None)  # GL_FLOAT=0x1406
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 2, 0x1406, False, 16, 8)

        self._program = compileProgram(
            compileShader(VERT_SHADER, 0x8B31),   # GL_VERTEX_SHADER
            compileShader(FRAG_SHADER, 0x8B30),   # GL_FRAGMENT_SHADER
        )
        self._tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self._tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        self._tex_edges = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self._tex_edges)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        self._tex_dist = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self._tex_dist)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT)
        if self._pending_grid is not None:
            self._upload_grid(self._pending_grid)
            self._pending_grid = None
        if self._pending_edges is not None:
            self._upload_edges(self._pending_edges)
            self._pending_edges = None
        if self._pending_dist is not None:
            self._upload_dist(self._pending_dist)
            self._pending_dist = None
        glUseProgram(self._program)
        glBindVertexArray(self._vao)
        # Bind textures to units 0,1,2
        glBindTexture(GL_TEXTURE_2D, self._tex)
        glUniform1i(glGetUniformLocation(self._program, 'uTex'), 0)
        glBindTexture(GL_TEXTURE_2D, self._tex_edges)
        glUniform1i(glGetUniformLocation(self._program, 'uEdges'), 0)  # share unit for simplicity
        glBindTexture(GL_TEXTURE_2D, self._tex_dist)
        glUniform1i(glGetUniformLocation(self._program, 'uDist'), 0)
        loc_sz = glGetUniformLocation(self._program, 'uTexSize')
        glUniform2f(loc_sz, float(self._grid_tex_size[0]), float(self._grid_tex_size[1]))
        # Toggles
        glUniform1i(glGetUniformLocation(self._program, 'uEnableOutline'), int(self._toggles['outline']))
        glUniform1i(glGetUniformLocation(self._program, 'uEnableRays'), int(self._toggles['rays']))
        glUniform1i(glGetUniformLocation(self._program, 'uEnableEcho'), int(self._toggles['echo']))
        glUniform1i(glGetUniformLocation(self._program, 'uEnableSparkles'), int(self._toggles['sparkles']))
        glUniform1i(glGetUniformLocation(self._program, 'uEnableBackground'), int(self._toggles['bg']))
        # Bands
        for i in range(6):
            glUniform1f(glGetUniformLocation(self._program, f'uBands[{i}]'), float(self._bands[i]))
        glUniform1f(glGetUniformLocation(self._program, 'uTime'), float(self._time))
        # Params
        glUniform1f(glGetUniformLocation(self._program, 'uRaysLength'), float(self._params['raysLength']))
        glUniform1f(glGetUniformLocation(self._program, 'uRaysIntensity'), float(self._params['raysIntensity']))
        glUniform1f(glGetUniformLocation(self._program, 'uEchoSpacing'), float(self._params['echoSpacing']))
        glUniform1f(glGetUniformLocation(self._program, 'uEchoBand'), float(self._params['echoBand']))
        glUniform1i(glGetUniformLocation(self._program, 'uEchoLines'), int(self._params['echoLines']))
        glUniform1f(glGetUniformLocation(self._program, 'uSparklesDensity'), float(self._params['sparklesDensity']))
        glUniform1f(glGetUniformLocation(self._program, 'uSparklesGain'), float(self._params['sparklesGain']))
        glUniform1f(glGetUniformLocation(self._program, 'uBgIntensity'), float(self._params['bgIntensity']))
        glUniform1f(glGetUniformLocation(self._program, 'uBgSpeed'), float(self._params['bgSpeed']))
        glDrawArrays(GL_TRIANGLES, 0, 6)

    def update_grid(self, grid: np.ndarray):
        # grid: 2D float32 [0..1] or uint8 [0..255]
        self._pending_grid = grid
        self.update()

    def _upload_grid(self, grid):
        if grid.dtype != np.uint8:
            g = np.clip(grid, 0.0, 1.0)
            g = (g * 255.0).astype(np.uint8)
        else:
            g = grid
        h, w = g.shape
        self._grid_tex_size = (w, h)
        glBindTexture(GL_TEXTURE_2D, self._tex)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RED, w, h, 0, GL_RED, GL_UNSIGNED_BYTE, g)

    def _upload_edges(self, edges):
        e = np.clip(edges, 0.0, 1.0)
        e = (e * 255.0).astype(np.uint8)
        h, w = e.shape
        glBindTexture(GL_TEXTURE_2D, self._tex_edges)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RED, w, h, 0, GL_RED, GL_UNSIGNED_BYTE, e)

    def _upload_dist(self, dist):
        # Normalize distance to 0..1 based on max dimension heuristics
        d = np.asarray(dist, dtype=np.float32)
        scale = max(1.0, float(max(self._grid_tex_size)))
        dn = np.clip(d / scale, 0.0, 1.0)
        dn = (dn * 255.0).astype(np.uint8)
        h, w = dn.shape
        glBindTexture(GL_TEXTURE_2D, self._tex_dist)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RED, w, h, 0, GL_RED, GL_UNSIGNED_BYTE, dn)

    # Public setters
    def update_edges_dist(self, edges: np.ndarray, dist: np.ndarray):
        self._pending_edges = edges
        self._pending_dist = dist
        self.update()

    def set_toggles(self, outline: bool, rays: bool, echo: bool, sparkles: bool, bg: bool):
        self._toggles['outline'] = 1 if outline else 0
        self._toggles['rays'] = 1 if rays else 0
        self._toggles['echo'] = 1 if echo else 0
        self._toggles['sparkles'] = 1 if sparkles else 0
        self._toggles['bg'] = 1 if bg else 0

    def set_bands(self, bands: np.ndarray):
        if bands is None:
            self._bands[:] = 0.0
        else:
            self._bands[:] = np.asarray(bands, dtype=np.float32)[:6]

    def set_params(self, **kwargs):
        for k, v in kwargs.items():
            if k in self._params:
                self._params[k] = float(v) if not isinstance(v, (int,)) else int(v)

    def set_time(self, t: float):
        self._time = float(t)


