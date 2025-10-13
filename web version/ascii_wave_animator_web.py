#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ASCII Wave Animator - Web Version
Запуск: python ascii_wave_animator_web.py
Откроется браузер на http://localhost:5000
"""

import os
import sys
import math
import base64
import io
import json
import webbrowser
from pathlib import Path
from threading import Timer

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, render_template_string, request, jsonify, send_file

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

# ASCII ramps
ASCII_RAMP_PURE = " .:-=+*#%@"
ASCII_RAMP_EXT = " .`^\",:;Il!i><~+_-?][}{1)(|/\\tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$█"

# Utility functions
def clamp01(x):
    return np.clip(x, 0.0, 1.0)

def to_grayscale(arr):
    if len(arr.shape) == 2:  # Already grayscale
        return arr.astype(np.float32) / 255.0
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return (y / 255.0).astype(np.float32)

def resize_to_char_grid(img_gray, cols, rows):
    h, w = img_gray.shape
    pil = Image.fromarray((img_gray * 255).astype(np.uint8)).convert('L')
    pil = pil.resize((cols, rows), Image.BICUBIC)
    grid = np.array(pil, dtype=np.float32) / 255.0
    return grid

def apply_waves_time(base_gray, t, params):
    rows, cols = base_gray.shape
    yy, xx = np.mgrid[0:rows, 0:cols].astype(np.float32)
    x = xx / max(1, cols)
    y = yy / max(1, rows)
    A = 1.0 - base_gray
    
    phase_x = 2 * math.pi * (params['freq_x'] * x + 0.1) + t * params['speed_x']
    phase_y = 2 * math.pi * (params['freq_y'] * y + 0.3) + t * params['speed_y']
    W = np.sin(phase_x) * A + np.sin(phase_y) * (1.0 - A * 0.5)
    
    phase_xy = 2 * math.pi * (0.35 * (x + y)) + t * 0.7
    W += 0.6 * np.sin(phase_xy) * (0.5 + 0.5 * np.sin(phase_x) * np.sin(phase_y))
    
    out = base_gray + params['amplitude'] * W
    
    if params['contrast'] != 1.0:
        mid = 0.5
        out = clamp01((out - mid) * params['contrast'] + mid)
    
    return clamp01(out)

def generate_random_shapes(width, height, n=30, angularity=0.5):
    img = Image.new("L", (width, height), 0)
    d = ImageDraw.Draw(img, 'L')
    
    for i in range(n):
        cx = np.random.randint(0, width)
        cy = np.random.randint(0, height)
        r = np.random.randint(min(width, height) // 20, min(width, height) // 5)
        sides = int(3 + (1 - angularity) * 5 + angularity * 20)
        
        pts = []
        for k in range(sides):
            a = 2 * math.pi * k / sides + np.random.random() * 0.2 * angularity
            rr = r * (0.7 + 0.6 * np.random.random() * angularity)
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        
        fill = int(np.random.randint(80, 240))
        d.polygon(pts, fill=fill)
    
    arr = np.array(img, dtype=np.float32) / 255.0
    return arr

def gray_to_ascii(gray, ramp, invert=False):
    n = len(ramp) - 1
    v_for_char = gray if invert else 1.0 - gray
    indices = np.round(v_for_char * n).astype(int)
    indices = np.clip(indices, 0, n)
    
    rows, cols = gray.shape
    ascii_art = []
    for row in range(rows):
        line = ''.join(ramp[indices[row, col]] for col in range(cols))
        ascii_art.append(line)
    
    return '\n'.join(ascii_art)

def get_color_for_value(val, color_stops):
    t = np.clip(val, 0, 1)
    seg = min(3, int(t * 4))
    seg_t0 = seg * 0.25
    local_t = (t - seg_t0) / 0.25
    
    c1 = color_stops[seg]
    c2 = color_stops[seg + 1]
    
    return [
        int(c1[0] + (c2[0] - c1[0]) * local_t),
        int(c1[1] + (c2[1] - c1[1]) * local_t),
        int(c1[2] + (c2[2] - c1[2]) * local_t)
    ]

# HTML Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ASCII Wave Animator</title>
    <link href="https://fonts.googleapis.com/css?family=Helvetica+Neue&display=swap" rel="stylesheet">
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Helvetica Neue', Arial, sans-serif;
            background: #0b0b0b;
            color: #fff;
            overflow-x: hidden;
            font-size: 14px;
        }

        .container {
            width: 100%;
            min-height: 100vh;
            display: flex;
            padding: 20px;
            gap: 20px;
        }

        .preview-section {
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 16px;
            min-width: 0;
        }

        .preview-canvas {
            flex: 1;
            background: #000;
            border-radius: 30px;
            overflow: auto;
            position: relative;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 500px;
        }

        #asciiCanvas {
            font-family: 'Courier New', monospace;
            line-height: 1;
            white-space: pre;
            font-size: 8px;
            padding: 20px;
        }

        .toolbar {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }

        .btn {
            background: #000;
            border: 2px solid #fff;
            border-radius: 20px;
            padding: 12px 24px;
            color: #fff;
            font-size: 16px;
            cursor: pointer;
            transition: background 0.2s;
            font-family: 'Helvetica Neue', Arial, sans-serif;
        }

        .btn:hover {
            background: #222;
        }

        .btn.primary {
            background: #fff;
            color: #000;
        }

        .btn.primary:hover {
            background: #eee;
        }

        .btn.icon {
            width: 44px;
            height: 44px;
            padding: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
        }

        .controls-section {
            width: 557px;
            display: flex;
            flex-direction: column;
            gap: 16px;
            flex-shrink: 0;
        }

        .tabs {
            background: transparent;
            display: flex;
            gap: 0;
        }

        .tab {
            background: #000;
            border: none;
            border-top-left-radius: 20px;
            border-top-right-radius: 20px;
            padding: 13px 22px;
            color: #fff;
            font-size: 20px;
            cursor: pointer;
            opacity: 0.5;
            transition: opacity 0.2s;
            font-family: 'Helvetica Neue', Arial, sans-serif;
            font-weight: 500;
        }

        .tab.active {
            opacity: 1;
        }

        .tab-content {
            display: none;
            background: #000;
            border-radius: 30px;
            padding: 20px;
            max-height: calc(100vh - 200px);
            overflow-y: auto;
        }

        .tab-content.active {
            display: block;
        }

        .control-group {
            background: #000;
            border: 2px solid #fff;
            border-radius: 20px;
            padding: 30px 20px;
            margin-bottom: 10px;
        }

        .control-group-title {
            font-size: 16px;
            font-weight: 300;
            margin-bottom: 20px;
            padding-left: 5px;
        }

        .control-row {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 10px;
        }

        .control-label {
            font-size: 16px;
            flex: 0 0 120px;
        }

        .stepper {
            display: flex;
            gap: 8px;
            align-items: center;
            margin-left: auto;
        }

        .stepper-value {
            background: #000;
            border: 2px solid #fff;
            border-radius: 10px;
            padding: 10px;
            min-width: 68px;
            text-align: center;
            font-size: 24px;
            font-weight: bold;
        }

        .stepper-btn {
            background: #000;
            border: 2px solid #fff;
            width: 44px;
            height: 40px;
            color: #fff;
            font-size: 20px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            user-select: none;
        }

        .stepper-btn:first-of-type {
            border-radius: 50px 0 0 50px;
        }

        .stepper-btn:last-of-type {
            border-radius: 0 50px 50px 0;
        }

        .stepper-btn:hover {
            background: #222;
        }

        .slider-container {
            flex: 1;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .slider {
            flex: 1;
            height: 2px;
            background: #fff;
            border-radius: 1px;
            position: relative;
            cursor: pointer;
        }

        .slider-thumb {
            width: 16px;
            height: 16px;
            background: #fff;
            border-radius: 50%;
            position: absolute;
            top: 50%;
            transform: translate(-50%, -50%);
            cursor: grab;
        }

        .slider-thumb:active {
            cursor: grabbing;
        }

        .checkbox-row {
            display: flex;
            align-items: center;
            gap: 12px;
            margin: 15px 0;
        }

        .checkbox {
            width: 23px;
            height: 23px;
            background: #000;
            border: 2px solid #fff;
            border-radius: 20px;
            cursor: pointer;
            position: relative;
        }

        .checkbox.checked::after {
            content: '';
            position: absolute;
            width: 13px;
            height: 13px;
            background: #fff;
            border-radius: 50%;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
        }

        input[type="file"] {
            display: none;
        }

        .color-stop-row {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 12px;
        }

        .color-swatch {
            width: 30px;
            height: 30px;
            border: 2px solid #fff;
            border-radius: 8px;
            cursor: pointer;
        }

        .color-input {
            background: #000;
            border: 2px solid #fff;
            border-radius: 10px;
            padding: 8px 12px;
            color: #fff;
            font-family: monospace;
            flex: 1;
        }

        input[type="color"] {
            opacity: 0;
            position: absolute;
            pointer-events: none;
        }

        @media (max-width: 1400px) {
            .container {
                flex-direction: column;
            }
            .controls-section {
                width: 100%;
            }
        }

        .loading {
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: #000;
            border: 2px solid #fff;
            border-radius: 20px;
            padding: 30px;
            display: none;
            z-index: 1000;
        }

        .loading.show {
            display: block;
        }
    </style>
</head>
<body>
    <div class="loading" id="loading">Загрузка...</div>
    
    <div class="container">
        <div class="preview-section">
            <div class="preview-canvas" id="previewCanvas">
                <pre id="asciiCanvas"></pre>
            </div>
            <div class="toolbar">
                <button class="btn" id="btnImport">импорт 📁</button>
                <button class="btn" id="btnGenerate">генерация паттерна</button>
                <button class="btn primary" id="btnExport">Экспорт 💾</button>
                <div style="flex: 1"></div>
                <button class="btn icon" id="btnPlayPause">▶</button>
            </div>
            <input type="file" id="fileInput" accept="image/*">
        </div>

        <div class="controls-section">
            <div class="tabs">
                <button class="tab active" data-tab="canvas">Настройки холста</button>
                <button class="tab" data-tab="color">Цвет</button>
                <button class="tab" data-tab="mode">Режимы</button>
                <button class="tab" data-tab="export">Экспорт</button>
            </div>

            <div class="tab-content active" id="tab-canvas">
                <div class="control-group">
                    <div class="control-group-title">Сетка</div>
                    <div class="control-row">
                        <span class="control-label">столбцы</span>
                        <div class="stepper">
                            <div class="stepper-value" id="colsValue">80</div>
                            <div style="display: flex;">
                                <button class="stepper-btn" id="colsMinus">-</button>
                                <button class="stepper-btn" id="colsPlus">+</button>
                            </div>
                        </div>
                    </div>
                    <div class="control-row">
                        <span class="control-label">строки</span>
                        <div class="stepper">
                            <div class="stepper-value" id="rowsValue">40</div>
                            <div style="display: flex;">
                                <button class="stepper-btn" id="rowsMinus">-</button>
                                <button class="stepper-btn" id="rowsPlus">+</button>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="control-group">
                    <div class="control-group-title">символы</div>
                    <div class="checkbox-row">
                        <div class="checkbox" id="extendedCheck"></div>
                        <span>расширенный набор</span>
                    </div>
                </div>

                <div class="control-group">
                    <div class="control-group-title">волны</div>
                    <div class="control-row">
                        <span class="control-label">частота X:</span>
                        <div class="slider-container">
                            <div class="slider" data-param="freq_x" data-min="0" data-max="3">
                                <div class="slider-thumb" style="left: 27%"></div>
                            </div>
                        </div>
                    </div>
                    <div class="control-row">
                        <span class="control-label">частота Y:</span>
                        <div class="slider-container">
                            <div class="slider" data-param="freq_y" data-min="0" data-max="3">
                                <div class="slider-thumb" style="left: 20%"></div>
                            </div>
                        </div>
                    </div>
                    <div class="control-row">
                        <span class="control-label">скорость X:</span>
                        <div class="slider-container">
                            <div class="slider" data-param="speed_x" data-min="-3" data-max="3">
                                <div class="slider-thumb" style="left: 70%"></div>
                            </div>
                        </div>
                    </div>
                    <div class="control-row">
                        <span class="control-label">скорость Y:</span>
                        <div class="slider-container">
                            <div class="slider" data-param="speed_y" data-min="-3" data-max="3">
                                <div class="slider-thumb" style="left: 35%"></div>
                            </div>
                        </div>
                    </div>
                    <div class="control-row">
                        <span class="control-label">амплитуда</span>
                        <div class="slider-container">
                            <div class="slider" data-param="amplitude" data-min="0" data-max="2">
                                <div class="slider-thumb" style="left: 12.5%"></div>
                            </div>
                        </div>
                    </div>
                    <div class="control-row">
                        <span class="control-label">контраст</span>
                        <div class="slider-container">
                            <div class="slider" data-param="contrast" data-min="0.5" data-max="2.5">
                                <div class="slider-thumb" style="left: 25%"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="tab-content" id="tab-color">
                <div class="control-group">
                    <div class="control-group-title">цвет</div>
                    <div id="colorStops"></div>
                    <div class="checkbox-row">
                        <div class="checkbox" id="invertCheck"></div>
                        <span>инвертировать яркость</span>
                    </div>
                    <button class="btn" id="btnRandomPalette" style="width: 100%; margin-top: 10px;">рандом палитра 🎲</button>
                </div>
            </div>

            <div class="tab-content" id="tab-mode">
                <div class="control-group">
                    <div class="control-group-title">режимы</div>
                    <div class="control-row">
                        <span class="control-label">режим</span>
                        <select id="modeSelect" style="flex: 1; background: #000; color: #fff; border: 2px solid #fff; border-radius: 20px; padding: 12px; font-size: 16px;">
                            <option value="waves">волны</option>
                            <option value="static">статичный</option>
                        </select>
                    </div>
                </div>
            </div>

            <div class="tab-content" id="tab-export">
                <div class="control-group">
                    <div class="control-group-title">экспорт</div>
                    <div class="control-row">
                        <span class="control-label">формат</span>
                        <select id="formatSelect" style="flex: 1; background: #000; color: #fff; border: 2px solid #fff; border-radius: 20px; padding: 12px; font-size: 16px;">
                            <option value="txt">TXT</option>
                            <option value="png">PNG (скоро)</option>
                        </select>
                    </div>
                    <button class="btn primary" id="btnDownload" style="width: 100%; margin-top: 15px;">скачать</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        const state = {
            imageData: null,
            cols: 80,
            rows: 40,
            useExtended: false,
            invert: false,
            playing: false,
            time: 0,
            mode: 'waves',
            params: {
                freq_x: 0.8,
                freq_y: 0.6,
                speed_x: 1.2,
                speed_y: -0.9,
                amplitude: 0.25,
                contrast: 1.0
            },
            colorStops: [
                [255, 255, 255],
                [255, 255, 255],
                [255, 255, 255],
                [255, 255, 255],
                [255, 255, 255]
            ]
        };

        function showLoading() {
            document.getElementById('loading').classList.add('show');
        }

        function hideLoading() {
            document.getElementById('loading').classList.remove('show');
        }

        async function renderASCII() {
            if (!state.imageData) return;

            const data = {
                image_data: state.imageData,
                cols: state.cols,
                rows: state.rows,
                use_extended: state.useExtended,
                invert: state.invert,
                time: state.time,
                mode: state.mode,
                params: state.params,
                color_stops: state.colorStops
            };

            try {
                const response = await fetch('/render', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });

                const result = await response.json();
                document.getElementById('asciiCanvas').innerHTML = result.html;
            } catch (error) {
                console.error('Render error:', error);
            }
        }

        function animate() {
            if (state.playing) {
                state.time += 0.04;
                renderASCII();
            }
            requestAnimationFrame(animate);
        }

        // Event handlers
        document.getElementById('btnImport').addEventListener('click', () => {
            document.getElementById('fileInput').click();
        });

        document.getElementById('fileInput').addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            showLoading();
            const formData = new FormData();
            formData.append('file', file);

            try {
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();
                state.imageData = result.image_data;
                await renderASCII();
            } catch (error) {
                console.error('Upload error:', error);
                alert('Ошибка загрузки изображения');
            } finally {
                hideLoading();
            }
        });

        document.getElementById('btnGenerate').addEventListener('click', async () => {
            showLoading();
            try {
                const response = await fetch('/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ width: 512, height: 512, angularity: 0.5 })
                });

                const result = await response.json();
                state.imageData = result.image_data;
                await renderASCII();
            } catch (error) {
                console.error('Generate error:', error);
            } finally {
                hideLoading();
            }
        });

        document.getElementById('btnPlayPause').addEventListener('click', (e) => {
            state.playing = !state.playing;
            e.target.textContent = state.playing ? '⏸' : '▶';
        });

        document.getElementById('btnRandomPalette').addEventListener('click', () => {
            for (let i = 0; i < 5; i++) {
                if (Math.random() < 0.25) {
                    const g = Math.floor(Math.random() * 256);
                    state.colorStops[i] = [g, g, g];
                } else {
                    state.colorStops[i] = [
                        Math.floor(Math.random() * 256),
                        Math.floor(Math.random() * 256),
                        Math.floor(Math.random() * 256)
                    ];
                }
            }
            updateColorUI();
            renderASCII();
        });

        document.getElementById('btnDownload').addEventListener('click', async () => {
            const format = document.getElementById('formatSelect').value;
            
            if (format === 'txt') {
                const ascii = document.getElementById('asciiCanvas').innerText;
                const blob = new Blob([ascii], { type: 'text/plain' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'ascii_art.txt';
                a.click();
                URL.revokeObjectURL(url);
            } else {
                alert('PNG экспорт в разработке');
            }
        });

        // Stepper controls
        function setupStepper(id, getValue, setValue, min, max) {
            document.getElementById(`${id}Minus`).addEventListener('click', () => {
                const val = Math.max(min, getValue() - 1);
                setValue(val);
                document.getElementById(`${id}Value`).textContent = val;
                renderASCII();
            });

            document.getElementById(`${id}Plus`).addEventListener('click', () => {
                const val = Math.min(max, getValue() + 1);
                setValue(val);
                document.getElementById(`${id}Value`).textContent = val;
                renderASCII();
            });
        }

        setupStepper('cols', () => state.cols, (v) => state.cols = v, 8, 200);
        setupStepper('rows', () => state.rows, (v) => state.rows = v, 8, 100);

        // Checkbox controls
        document.getElementById('extendedCheck').addEventListener('click', function() {
            this.classList.toggle('checked');
            state.useExtended = this.classList.contains('checked');
            renderASCII();
        });

        document.getElementById('invertCheck').addEventListener('click', function() {
            this.classList.toggle('checked');
            state.invert = this.classList.contains('checked');
            renderASCII();
        });

        // Tab controls
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                tab.classList.add('active');
                document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');
            });
        });

        // Slider controls
        document.querySelectorAll('.slider').forEach(slider => {
            const thumb = slider.querySelector('.slider-thumb');
            const param = slider.dataset.param;
            const min = parseFloat(slider.dataset.min);
            const max = parseFloat(slider.dataset.max);
            let isDragging = false;

            function updateValue(clientX) {
                const rect = slider.getBoundingClientRect();
                const percent = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
                thumb.style.left = (percent * 100) + '%';
                state.params[param] = min + percent * (max - min);
                renderASCII();
            }

            thumb.addEventListener('mousedown', (e) => {
                isDragging = true;
                e.preventDefault();
            });

            slider.addEventListener('click', (e) => {
                if (e.target === slider) updateValue(e.clientX);
            });

            document.addEventListener('mousemove', (e) => {
                if (isDragging) updateValue(e.clientX);
            });

            document.addEventListener('mouseup', () => {
                isDragging = false;
            });
        });

        // Color stops UI
        function updateColorUI() {
            const container = document.getElementById('colorStops');
            container.innerHTML = '';

            state.colorStops.forEach((color, i) => {
                const row = document.createElement('div');
                row.className = 'color-stop-row';

                const label = document.createElement('span');
                label.textContent = `${i + 1}`;
                label.style.flex = '0 0 30px';

                const swatch = document.createElement('div');
                swatch.className = 'color-swatch';
                swatch.style.background = `rgb(${color[0]},${color[1]},${color[2]})`;

                const input = document.createElement('input');
                input.type = 'color';
                input.value = `#${color[0].toString(16).padStart(2,'0')}${color[1].toString(16).padStart(2,'0')}${color[2].toString(16).padStart(2,'0')}`;

                input.addEventListener('change', (e) => {
                    const hex = e.target.value;
                    const r = parseInt(hex.substr(1, 2), 16);
                    const g = parseInt(hex.substr(3, 2), 16);
                    const b = parseInt(hex.substr(5, 2), 16);
                    state.colorStops[i] = [r, g, b];
                    swatch.style.background = `rgb(${r},${g},${b})`;
                    hexInput.value = hex;
                    renderASCII();
                });

                swatch.addEventListener('click', () => input.click());

                const hexInput = document.createElement('input');
                hexInput.type = 'text';
                hexInput.className = 'color-input';
                hexInput.value = input.value;
                hexInput.maxLength = 7;

                hexInput.addEventListener('change', (e) => {
                    const hex = e.target.value;
                    if (/^#[0-9A-Fa-f]{6}$/.test(hex)) {
                        const r = parseInt(hex.substr(1, 2), 16);
                        const g = parseInt(hex.substr(3, 2), 16);
                        const b = parseInt(hex.substr(5, 2), 16);
                        state.colorStops[i] = [r, g, b];
                        swatch.style.background = `rgb(${r},${g},${b})`;
                        input.value = hex;
                        renderASCII();
                    }
                });

                row.appendChild(label);
                row.appendChild(swatch);
                row.appendChild(input);
                row.appendChild(hexInput);
                container.appendChild(row);
            });
        }

        // Mode selector
        document.getElementById('modeSelect').addEventListener('change', (e) => {
            state.mode = e.target.value;
            renderASCII();
        });

        // Initialize
        updateColorUI();
        
        // Generate default pattern on load
        document.getElementById('btnGenerate').click();
        
        // Start animation loop
        animate();
    </script>
</body>
</html>
"""

# Flask routes
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/upload', methods=['POST'])
def upload_image():
    try:
        file = request.files['file']
        img = Image.open(file.stream).convert('RGB')
        arr = np.array(img, dtype=np.uint8)
        
        # Return as base64 for client-side storage
        gray = to_grayscale(arr)
        img_bytes = io.BytesIO()
        Image.fromarray((gray * 255).astype(np.uint8)).save(img_bytes, format='PNG')
        img_base64 = base64.b64encode(img_bytes.getvalue()).decode()
        
        return jsonify({
            'success': True,
            'image_data': img_base64
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/generate', methods=['POST'])
def generate_pattern():
    try:
        data = request.json
        width = data.get('width', 512)
        height = data.get('height', 512)
        angularity = data.get('angularity', 0.5)
        
        arr = generate_random_shapes(width, height, n=30, angularity=angularity)
        
        img_bytes = io.BytesIO()
        Image.fromarray((arr * 255).astype(np.uint8)).save(img_bytes, format='PNG')
        img_base64 = base64.b64encode(img_bytes.getvalue()).decode()
        
        return jsonify({
            'success': True,
            'image_data': img_base64
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/render', methods=['POST'])
def render_ascii():
    try:
        data = request.json
        
        # Decode image
        img_base64 = data['image_data']
        img_bytes = base64.b64decode(img_base64)
        img = Image.open(io.BytesIO(img_bytes)).convert('L')
        gray = np.array(img, dtype=np.float32) / 255.0
        
        # Resize to grid
        cols = data['cols']
        rows = data['rows']
        gray_resized = resize_to_char_grid(gray, cols, rows)
        
        # Apply waves if needed
        if data['mode'] == 'waves':
            gray_resized = apply_waves_time(gray_resized, data['time'], data['params'])
        
        # Convert to ASCII with colors
        ramp = ASCII_RAMP_EXT if data['use_extended'] else ASCII_RAMP_PURE
        invert = data['invert']
        color_stops = data['color_stops']
        
        html_output = gray_to_ascii_html(gray_resized, ramp, color_stops, invert)
        
        return jsonify({
            'success': True,
            'html': html_output
        })
    except Exception as e:
        print(f"Render error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

def gray_to_ascii_html(gray, ramp, color_stops, invert=False):
    """Convert grayscale array to colored HTML ASCII art"""
    n = len(ramp) - 1
    rows, cols = gray.shape
    html_lines = []
    
    for row in range(rows):
        line_html = []
        for col in range(cols):
            v = float(gray[row, col])
            v_for_char = v if invert else 1.0 - v
            idx = int(np.clip(v_for_char * n + 0.5, 0, n))
            ch = ramp[idx]
            
            color = get_color_for_value(v, color_stops)
            line_html.append(f'<span style="color:rgb({color[0]},{color[1]},{color[2]})">{ch}</span>')
        
        html_lines.append(''.join(line_html))
    
    return '\n'.join(html_lines)

def open_browser():
    """Open browser after short delay"""
    webbrowser.open('http://localhost:5000')

if __name__ == '__main__':
    print("=" * 60)
    print("ASCII Wave Animator - Web Version")
    print("=" * 60)
    print("\n🚀 Запуск сервера на http://localhost:5000")
    print("📱 Браузер откроется автоматически через 1.5 секунды...")
    print("\n⚠️  Для остановки нажмите Ctrl+C\n")
    print("=" * 60)
    
    # Open browser after delay
    Timer(1.5, open_browser).start()
    
    # Run Flask app
    app.run(debug=False, port=5000, threaded=True)