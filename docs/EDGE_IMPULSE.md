# Edge Impulse practice run

Goal: train one ball and goal detector before Saturday, so on the day the steps are familiar and
`model_runner.py` has a real model to run. About an hour, most of it waiting for training. It uses
the guide's settings (`upstream/robocar/README.md`, "Edge Impulse: train a detector") and the
organizers' August dataset: 321 pictures from the robot's own camera, labelled goal, robot and
soccer_ball.

![Training happens once, online, and exports model.eim; on the robot the same file runs on every frame, offline: that is on-device AI](../figs/on-device-ai.svg)

## Steps

1. Make a free account at studio.edgeimpulse.com. This needs you; I can't create accounts.
2. Open the August dataset, studio.edgeimpulse.com/public/1085406/live, and click "Clone this
   project". Your copy has the labelled pictures, already split into training (255) and test
   (66).
3. Create impulse, with the guide's settings:
   - Image width 96, height 96, resize mode Squash.
   - Processing block: Image. Learning block: Object Detection (Images).
   - Save impulse.
4. Image (under Impulse design): color depth RGB, Save parameters, then Generate features.
5. Object detection: FOMO MobileNetV2 0.35, 150 to 180 training cycles, learning rate 0.001,
   training on CPU, data augmentation on. Save and train, then note the F1 score for each label.
6. Model testing: classify the test set and note the accuracy. This is the honest number, since
   the model never saw those pictures.
7. Deployment: choose Arduino UNO Q, build, and download the `.eim` file. Save it as
   `prep/models/robocar.eim`; `models/` is git-ignored, since the model comes from your own
   account. If Edge Impulse also offers a macOS build, download that too, as
   `prep/models/robocar-mac.eim`, to run it on the laptop.

## Trying it on the laptop

The runner needs an `.eim` built for the machine it runs on: the UNO Q build only runs on the
board. With a macOS build, point `model.path` at it in a copy of the config and run the demo with
the model. No `chmod` is needed: the runner gives a model back its run permission when an unzip
or a download has dropped it.

```bash
uv run python demo.py --source 0 --show --detector model --config my_config.json
```

The synthetic video's ball is drawn, not photographed, so a model trained on real pictures may
not find it. A real soccer ball in front of the webcam is the better test.

## On the day

What the organizers said and did on Oct 24. In the late morning the guide's project
(studio.edgeimpulse.com/public/1144501/live) held their office pictures, 321 labelled goal, robot
and soccer_ball (the August set), and an organizer advised taking about 50 phone pictures of the
ball and 50 of the goals in the room until a bigger set from the room was ready. At 12:05 they
replaced the project's pictures with 353 new ones (281 for training, 72 for testing), labelled
`soccerball` and `goal`, with no robot class. They are square, 512 by 512, and the one checked
shows a pale yellow ball on carpet, so they are probably from the event room. A few were uploaded
without their boxes, and the organizer said they would fix those.

![Your first model today in six steps: clone the organizers' project, box or delete the 6 pictures with no boxes, train a small model, download the .eim file, onto the board, a watch-only test, then your own pictures and train again](../figs/todays-model.svg)

1. Sign in at studio.edgeimpulse.com, open the guide's project and click "Clone this project".
   A clone is a copy made at that moment, so fixes to their project after it don't reach yours.
   At 12:35, 6 of the 353 pictures still had no boxes (3 for training, 3 for testing; read from
   Edge Impulse's public API), few enough to fix in your copy instead of waiting.
2. In your copy, check that every picture has its boxes: Data acquisition lists each picture's
   labels. A picture of the ball with no box on it teaches the model that the ball is
   background, so label or delete any without.
3. Name any new boxes with the labels your copy already has, `soccerball` and `goal` since 12:05.
   A second spelling, such as `soccer_ball` from the August set, would split the ball into two
   classes that the model learns apart. The app accepts either spelling (`model.ball_labels`),
   but one model should use one.
4. Train with the settings in steps 3 to 5 above, deploy for Arduino UNO Q as in step 7, and
   download the `.eim`. The organizer's "150 epochs" are the guide's training cycles: an epoch is
   one pass through every training picture. Data augmentation, on in those settings, makes
   slightly changed copies of each picture while training, with noise and small turns, so the
   model meets more variety than was photographed.
5. Copy it into the app as `python/models/robocar.eim`, set `"detector": "model"` in the
   config's `run` section, and read the startup log: it prints the model's labels, and warns if
   none of `ball_labels` is among them. Test in watch-only mode first.
6. If the model misses things, add pictures and retrain. The robot's own camera gives the best
   ones (`demo.py --record`, then "Upload data" in Data acquisition), in separate sessions for
   training and for testing. Phone pictures work too: crouch to about the height of the robot's
   camera, and hold the phone sideways if the phone page keeps the phone's shape, as the picture
   below shows.

![A round ball squashed to 96 by 96: from the robot's 320 by 240 picture it is 12 wide and 16 tall; from a phone held upright, 16 wide and 12 tall; from a phone held sideways, 12 wide and 16 tall again](../figs/phone-sideways.svg)

The numbers come from drawing a round ball in a picture of each size and squashing it with
OpenCV's resize, the way Edge Impulse's Squash mode does. A model learns the shapes it is shown,
so pictures held upright teach it a ball the robot's camera never produces. The organizers'
square pictures keep the ball round, which is closer to the robot's 12 by 16 than an upright
phone picture's 16 by 12. The general idea has a name: a gap between the pictures a model is
trained on and the ones it meets later is called domain shift, and the office pictures had it
too, in color and light.

FOMO reports where the ball is, not how big it looks, so the controller judges "near" and
"close" by how low the ball sits in the picture as well. Calibrate `slow_y_frac` and
`close_y_frac` (see `CALIBRATION_LOG.md`).

### The guide's `edge-impulse-linux` line, and why this app skips it

Since Oct 24 the guide says to add `edge-impulse-linux` to the app's `python/requirements.txt`
while the board still has Internet, for the package's `ImageImpulseRunner`. This app doesn't
need it, because `model_runner.py` already does the same job, message for message. Both start
the model with a socket path, send `{"hello": 1}` and then `{"classify": [...]}` with a matching
`id`, read each reply up to its closing zero byte, and check its `success` field (compared with
the package's source, version 1.2.2). The package also has a shared-memory path, which it takes
only when the model offers one.

Adding it would be safe. Its other dependencies are already in the app's container, which sees
the system's packages: PyAudio 0.2.14, a microphone library it lists because the same package
also runs sound models, and six and numpy. App Lab also installs `requirements.txt` only when
the file changes. It would still add a download to an app that never calls it. If the real
model ever fails with `model_runner.py`, the board can rejoin the hotspot over USB and install
the package then, to compare the two.

The guide also mentions App Lab's Video Object Detection brick, which signs in to Edge Impulse
from App Lab. This app doesn't use it: it reads the robot's camera stream itself and runs the
model through `model_runner.py`.
