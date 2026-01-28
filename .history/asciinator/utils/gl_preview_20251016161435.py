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
    glUseProgram, glGetUniformLocation, glUniform1i, glUniform2f,
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
uniform sampler2D uTex;      // grayscale grid
uniform vec2 uTexSize;       // width, height in texels
void main() {
    // Sample grayscale grid and display as monochrome
    float g = texture(uTex, vUV).r;
    FragColor = vec4(vec3(g), 1.0);
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
        self._grid_tex_size = (1, 1)
        self._pending_grid = None  # numpy 2D uint8 or float [0..1]
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

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT)
        if self._pending_grid is not None:
            self._upload_grid(self._pending_grid)
            self._pending_grid = None
        glUseProgram(self._program)
        glBindVertexArray(self._vao)
        glBindTexture(GL_TEXTURE_2D, self._tex)
        loc_tex = glGetUniformLocation(self._program, 'uTex')
        glUniform1i(loc_tex, 0)
        loc_sz = glGetUniformLocation(self._program, 'uTexSize')
        glUniform2f(loc_sz, float(self._grid_tex_size[0]), float(self._grid_tex_size[1]))
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


