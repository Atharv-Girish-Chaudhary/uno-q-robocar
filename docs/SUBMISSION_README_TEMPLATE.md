# [Project name]: Robocar track, Build Day with Qualcomm 2026

[One or two sentences: what the robot does, and how it finds the ball and the goal.]

## Team

- [Name(s)]

## Source

- Repository or ZIP: [link or file name]
- `python/main.py`: the button-started run, from the guide's starter
- `python/detector.py`, `python/model_runner.py`: finding the ball and the goal
- `python/stream.py`: reading the camera, newest frame only, stall detection
- `python/controller.py`, `python/runloop.py`: the decision rules and the look, decide, move loop
- `python/robocar_config.json`: every threshold, speed and timing
- `sketch/`: the guide's motor sketch, unchanged [or describe changes]

## How to run it

1. [Import the ZIP in App Lab, or `make flash` from the app folder.]
2. Join the camera's Wi-Fi from the board: `sudo nmcli device wifi connect "[SSID]" password "[password]"`.
3. Raise the wheels, press BOOT on the camera, wait for the green light.
4. [Where to place the robot, the ball and the goal.]

## Camera settings

- Camera: Hiwonder ESP32-S3 (GC2145), 320 × 240 MJPEG at `http://192.168.5.1:81/stream`
- Network name: [SSID]
- Mounting and angle: [description]

## Detection

- Detector used: [color or Edge Impulse model]
- Color settings: [HSV ranges and search band from the config]
- Model: [Edge Impulse project, model type, input size, labels, accuracy on the test set]

## Motor calibration

| Direction | Speed | Duration (ms) | Movement | Surface | Battery (mV) |
|---|---|---|---|---|---|
| | | | | | |

`settle_ms`: [value], measured with the latency mode: [result].

## Behavior

[The rules in order: what makes the robot steer, approach, step around the ball, push, or stop.]

## Results

| Run | Start arrangement | Result | Time (s) | Notes |
|---|---|---|---|---|
| | | | | |

What went wrong and how it recovered: [lost ball, stale video, errors].

## Credits

- Event guide and starter code: Qualcomm Developer Relations, github.com/aaishikasb/uno-q-hackout
- Arduino UNO Q, App Lab and Arduino App CLI: Arduino
- miniAuto chassis and camera module: Hiwonder
- [Edge Impulse project and dataset, if used]
- OpenCV and numpy
