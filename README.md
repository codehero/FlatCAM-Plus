# FlatCAM Plus v1.0.0 (BETA) (c) 2026 - by Sadri ERCAN

**FlatCAM Plus** is a modernized fork of FlatCAM, a program for preparing CNC jobs for making PCBs on a CNC router. It takes Gerber files and creates G-Code for isolation routing, drilling, and more.

**Current version:** `1.0.0` beta, released `2026/05/03`.

Forked from the modern FlatCAM codebase maintained by Marius Stanciu (c) 2019.
Based on [FlatCAM](http://flatcam.org/) (c) 2014-2018 Juan Pablo Caram.

---

## Key Improvements

FlatCAM Plus modernizes the FlatCAM workflow with a stronger Windows runtime, cleaner manufacturing settings, more reliable CAM data handling, and an integrated CNC control workspace.

### Platform and Reliability

- **Modern runtime:** The project targets **Python 3.11+** and **PyQt6** for improved maintainability.
- **Windows-focused stability:** Core application behavior is tuned for current Windows environments.
- **Safer UI updates:** Background plotting and CNC UI refresh paths are hardened against deleted Qt/C++ wrapper errors.
- **Resilient plugin startup:** Optional dependency and plugin loading failures are handled more gracefully.
- **Unused plugin cleanup:** Removed disconnected, incomplete, or obsolete plugin remnants, including dead toolbar shortcuts, stale PDF-import hooks, the empty Geo Stitch editor plugin, and the unused standalone Transform plugin.
- **Dedicated CNC 3D Preview plugin:** A new standalone CNCJob preview plugin renders generated G-code jobs in a clean EasyEDA/Fusion-style 3D canvas with a standard PCB-green board, single-sided engraved Z-depth cut channels, a corner orbit gizmo, top/fit controls, middle-mouse panning, and modular sub-sections for future expansion.
- **Legacy 3D Area removed:** The old `Options -> Experimental -> 3D Area` entry and its legacy PlotCanvas3d implementation were removed in favor of the dedicated CNC 3D Preview plugin.
- **AI Assistant plugin:** A project-aware assistant panel can connect to OpenAI-compatible, local, Gemini, and Claude providers to analyze Gerber, Excellon, Geometry, and CNCJob context from inside FlatCAM Plus.
- **Coordinate-preserving imports:** Imported Gerber and Excellon files keep their source coordinates so copper, outline, and drill layers from the same CAM export stack remain aligned exactly as generated.
- **CNCJob compatibility hardening:** Older projects that do not carry Auto Levelling option keys now receive safe fallback defaults instead of failing during CNCJob creation.

### CAM and Tool Data

- **Improved geometry handling:** High-precision buffering and stable geometry unions improve Gerber visualization and toolpath reliability.
- **Database-backed tool setup:** Milling and isolation tools can use Tools Database records with automatic parameter mapping.
- **DB-first tool presets:** Cutting parameters belong to Tools Database presets; Preferences provide fallback defaults only when a preset or older project is missing a value.
- **Dynamic parameter sync:** Tool table, Milling parameters, and generated geometry are kept in sync before CNCJob generation.
- **CNCJob generation hardening:** Missing Milling defaults in older projects or database tools are completed automatically before G-code generation.
- **V-tool accuracy:** Shape, tip diameter, and related V-bit settings persist more reliably for isolation workflows.

### CNC Workflow

- **Integrated CNC controller:** Connection management, live status, jogging, machine profiles, work zeroing, job streaming, macros, terminal commands, SD jobs, and FluidNC file operations are available inside the CNC workspace.
- **Operational dashboard layout:** Feed/spindle status, G-code sender, position, jog, overrides, macros, job setup, preview, and terminal sections are arranged for direct machine operation.
- **Unified CNC-style workspace UI:** Preferences, the canvas tab area, the left sidebar, project trees, and selected Gerber/Excellon/CNCJob property panels now share the CNC Control visual language with clearer buttons and bordered panels.
- **CNC toolbar connection access:** The toolbar CNC connection/settings action opens the CNC connection modal directly, with serial, WiFi/TCP GRBL, and FluidNC Web/HTTP modes.
- **Offline G-code validation:** The CNC dashboard Preview and Verify actions work without an active controller connection and report clear status, warnings, and empty-job feedback.
- **Aspire-style job placement:** CNCJob coordinates can be remapped to a selected job size, origin, placement, and X/Y margin before preview or streaming, so material zeroing and design placement are handled inside the CNC Control workflow.
- **Job-size preview canvas:** The G-code preview panel includes a 2D material canvas that draws the selected job inside the configured PCB/work area, including origin, grid, margin guides, rapid moves, cutting moves, and outside-job warnings.
- **GRBL status visibility:** Homing state and active X/Y/Z limit inputs are normalized and shown in the CNC dashboard for clearer WiFi/TCP GRBL operation.
- **Machine-aware G-code metadata:** Exported G-code now records the active machine profile, travel limits, safe Z, and max spindle RPM as header comments, while Verify checks X/Y/Z motion bounds against the active profile.
- **Modular CNC architecture:** CNC controller features are split into focused modules under `appPlugins/cnc_control/` for easier maintenance and future plugin-style extensions.
- **Centralized manufacturing preferences:** Core machine setup starts from a dedicated Manufacturing Settings group before deeper plugin-specific defaults.

---

## New Features

### CNC Connection and Control

FlatCAM Plus includes a built-in CNC control workflow for managing machine sessions without leaving the application.

- **Connection dialog:** Serial, TCP/Telnet, and FluidNC Web/HTTP settings are managed from one modal.
- **Controller profiles:** FluidNC, GRBL, Smoothieware, Marlin, and generic G-code profiles provide controller-specific commands.
- **WiFi GRBL mode:** TCP/Telnet connections default to the GRBL profile, while Web/HTTP connections default to FluidNC.
- **Connection testing:** Selected transports can be tested before opening an active machine session.
- **Live machine status:** Controller reports update the toolbar, DRO, machine state, position, and controller details.
- **Limit input indicators:** Active GRBL `Pn:` limit inputs are shown beside X/Y/Z DRO rows and logged only when they change.
- **Safe disconnect:** Active transports, receiver threads, streaming state, and UI indicators are reset cleanly.

### CNC Dashboard

The CNC page is organized as a compact production dashboard:

- **Top row:** Feed and spindle indicators sit beside Machine Profiles and G-code job streaming.
- **Control row:** Position, Jog, Overrides & System, and Saved Macros share the same row for faster access.
- **Job setup row:** Job size, origin, placement, X/Y margins, and XY/Z/XYZ zero buttons sit next to G-Code Preview / Verification.
- **Preview row:** G-Code Preview / Verification displays the material canvas, selected job statistics, transformed G-code, and warnings before sending.
- **Terminal console:** Manual commands, TX/RX messages, warnings, errors, and polling controls are grouped below the machine controls with a taller console for longer GRBL sessions.

### Machine Profiles

- **Profile selector:** Switch between saved CNC machine configurations directly from the dashboard.
- **Profile settings:** Store safe Z, default jog feed, probe feed, max spindle RPM, and X/Y/Z travel limits.
- **Applied defaults:** Selecting a profile updates jog feed, spindle RPM limit, probe feed behavior, and machine summary.
- **Profile manager:** The **Manage** button opens a modal editor for creating, editing, deleting, and saving profiles.
- **Preferences access:** Profiles are also available under `Preferences -> Plugins -> Manufacturing Settings`.

### Manufacturing Preferences

- **Manufacturing Settings:** A top-level production group summarizes active machine setup in one predictable place.
- **Tool preset source:** Milling, Drilling, Cutout, Isolation, Paint, and NCC cutting values are intended to be configured in Tools Database presets.
- **Focused Milling defaults:** Core Milling settings are shown first; advanced, exclusion, polish, laser, and Excellon milling options are collapsed by default.
- **Focused Isolation defaults:** Common isolation routing controls are easier to reach while advanced options stay available when needed.
- **Fallback defaults:** Preferences remain available as safe defaults for new presets, missing DB keys, older project files, and non-preset workflows.
- **Backward compatibility:** Existing preference keys are preserved so saved defaults and project behavior continue to work.

### Job Setup, Placement, and Work Zeroing

- **Simplified setup panel:** The CNC dashboard uses a focused **Job Setup / Zero** panel instead of exposing probing, WCS, probe travel, plate, feed, and retract controls during normal job setup.
- **Job size:** Enter the real PCB/material size, such as `100 x 80 mm`, or use **Fit Size** to copy the selected CNCJob bounds.
- **Origin selection:** Choose the physical point to zero on the machine: Back-Left, Bottom-Left, Center, or raw absolute G-code XY.
- **Placement selection:** Place the selected CNCJob inside the job size independently from the machine zero point, including Same as Origin, Center, Bottom/Back left-center-right, and center-left/right alignments.
- **Margin control:** X/Y margins shrink the usable material area before placement, allowing repeatable edge clearance without editing the CAM source.
- **Work zeroing:** XY, Z, or XYZ work zero can be set with `G10 L20`; supported GRBL/FluidNC workflows activate `G54` automatically before zeroing and before queue streaming.
- **Transformed streaming:** `START QUEUE` streams the same transformed coordinates shown in preview, so the controller receives the job already mapped to the configured origin, placement, and margin.
- **Mapped bounds logging:** Before each streamed job, the terminal reports the mapped XY bounds so the operator can confirm placement numerically.

### Jobs, Preview, Files, and Macros

- **Direct job streaming:** Generated CNCJob objects can be streamed with progress tracking, pause/resume, and stop.
- **Job Queue / Sender:** Multiple CNCJob objects can be queued, reordered, removed, and streamed sequentially.
- **Queue progress:** The sender table shows queued, running, stopped, and completed jobs while the global progress bar tracks total queued lines.
- **G-Code Preview / Verification:** Selected jobs show line counts, motion statistics, bounds, estimated runtime, and safety warnings.
- **Material canvas preview:** The preview panel draws the selected CNCJob inside the configured job size, including grid, origin crosshair, margin guides, rapid/cut paths, path bounds, and outside-job warnings.
- **Mapped coordinate preview:** Preview and Verify analyze the transformed G-code used for streaming, not only the original plot-area coordinates.
- **Offline preview refresh:** Preview and Verify refresh the CNCJob list, read generated G-code from multiple CNCJob sources, and confirm successful analysis in the terminal even when no CNC is connected.
- **Verification checks:** The verifier flags missing units or positioning mode, cutting before spindle/feed setup, rapid XY motion below Z zero, pause commands, and X/Y/Z travel limit risks from the active machine profile.
- **Machine profile export notes:** G-code exports include the active profile name, travel limits, safe Z, and max spindle RPM as comments for traceability; controller firmware limits such as GRBL `$130/$131/$132` remain controller settings and are not overwritten by job files.
- **SD job control:** Supported controllers can list SD files and start selected SD jobs.
- **Flash File System modal:** FluidNC Web mode provides a modal file manager for listing, uploading, creating folders, deleting, navigating, and opening directories.
- **Saved Macros panel:** Saved macros are visible in the main control row, with a **Manage Macros** modal for editing macro names and G-code content.

### CNC Plugin Structure

The CNC control feature is organized as a plugin-like package under `appPlugins/cnc_control/`:

- `profiles.py` stores controller command profiles.
- `transports.py` contains Serial, TCP/Telnet, and FluidNC HTTP transport implementations.
- `widgets.py` contains reusable CNC widgets such as styled buttons, dashboard gauges, and the job-size G-code preview canvas.
- `machine_profiles.py` stores defaults and normalization helpers for machine profiles.
- `dialogs.py` contains modal workflows for Flash File System, macro management, and machine profile management.
- `sections.py` registers dashboard sections for gauges, machine profiles, job sender, G-code preview, position, jog, job setup, overrides, macros, terminal, and modal actions.
- `ui.py` assembles the CNC dashboard from registered sections.

### CNC 3D Preview Plugin Structure

The standalone CNC 3D preview feature is organized under `appPlugins/cnc_preview_3d/`:

- `renderer.py` owns the independent VisPy scene for CNCJob G-code rendering and draws cut paths as single-sided engraved Z-depth channels instead of mirrored or extruded underside geometry.
- `sections.py` registers modular preview panels for job selection and render stats.
- `ui.py` assembles the plugin page with a side control panel, full 3D canvas, corner orbit gizmo, top/fit controls, and middle-mouse panning support through the preview camera.

### AI Assistant Plugin Structure

The AI assistant feature is organized under `appPlugins/ai_assistant/`:

- `providers.py` contains OpenAI-compatible, OpenRouter, LM Studio, Ollama, Gemini, and Claude connection helpers.
- `dialogs.py` manages provider settings, API keys, model options, system prompts, and analysis context selection.
- `ui.py` assembles the assistant chat panel for project-aware PCB/CAM questions.

---

## Installation and Setup

### 1. Prerequisites
- **Python 3.11** or greater.
- **[Mamba](https://mamba.readthedocs.io/en/latest/installation.html)** or **[Conda](https://docs.conda.io/en/latest/miniconda.html)** (Recommended for dependency management).

### 2. Running from Sources

1. **Clone the repository:**
   ```bash
   git clone https://github.com/thebestgoodguy/flatcam.git
   cd flatcam
   ```

2. **Create the environment:**
   ```bash
   mamba env create -f environment.yml
   ```

3. **Activate the environment:**
   ```bash
   mamba activate flatcam
   ```

4. **Launch FlatCAM Plus:**
   ```bash
   python flatcam.py
   ```

### Manual Installation (pip)
If you prefer not to use Conda, you can install dependencies via pip:
```bash
pip install -r requirements.txt
python flatcam.py
```

---

## Support and Contact

- **Contact:** Reach out via the application menu:
  `Menu -> Help -> About FlatCAM Plus -> Programmers -> Sadri ERCAN`

---

## License

FlatCAM base code and MIT-licensed project components are covered by the root `LICENSE` file.

The CNC Control, CNC 3D Preview, and AI Assistant modules are licensed separately and are not covered by the root MIT license:

- `appPlugins/ToolCNCControl.py`
- `appPlugins/cnc_control/`
- `appPlugins/ToolCNCPreview3D.py`
- `appPlugins/cnc_preview_3d/`
- `appPlugins/ToolAIAssistant.py`
- `appPlugins/ai_assistant/`

See `appPlugins/cnc_control/LICENSE`, `appPlugins/cnc_preview_3d/LICENSE`, and `appPlugins/ai_assistant/LICENSE` for the separate module license terms. These modules may be used, studied, modified, and shared for non-commercial purposes, but they may not be sold, sublicensed, monetized, or included in a commercial product or service without separate written permission from Sadri ERCAN.
