# Questions for the organizers

Written before the event as the questions to ask at check-in, then answered on Oct 24 where the
day settled them. The office hours (Tue Oct 20, with the two judges) came first, and the event
page and the organizers' instructions answered questions 7 and 8 beforehand.

1. What are the "agreed conditions" for ball detection: ball color, lighting, distances,
   distractor objects?
   - Why it matters: it sets the detector's color and what to test. The guide's labels say
     "soccerball", and the August event used a black and white soccer ball.
   - Answer: never given as a list. On the day the ball was a small white soccer ball with black
     spots and the goal two yellow cones (questions 10 and 12).
2. How is the final run set up: fixed or randomized ball and goal positions, how many attempts,
   any time limit?
   - Why it matters: it sets `run_time_limit_s` and `max_pushes`, and decides how much the goal
     finder matters.
   - Answer: not settled in advance. The judges watched each team's runs after 4 PM, and teams
     could try again; the day's log in `NOTES.md` has the details.
3. The event page says the robocar that scores first wins, but the rubric has no speed criterion.
   Does speed count?
   - Why it matters: it decides how long and fast the pulses should be once the run is reliable.
   - Answer: not asked. The winning run was reported with its time, 7.12 s.
4. Can we bring a detector prepared in advance, or must everything be built on the day?
   - Why it matters: it decides whether the prep code and a pre-trained model can be used as
     they are.
   - Answer: yes, code written before the event is allowed (asked at check-in, Oct 24).
5. Which Wi-Fi network should the boards use for their first run, and does it need a login page?
   - Why it matters: the first run downloads and compiles the sketch's Arduino libraries, and a
     board without a screen can't get past a login page.
   - Answer: not asked at check-in. On the day the board had a phone hotspot saved for the
     Internet.
6. Arcade: does a RetroArch game count as original if we wrote it ourselves?
   - Why it matters: the Arcade rubric scores originality (20 points). Not this track, but worth
     knowing.
   - Answer: not asked (not this track).
7. How do prizes work for teams versus individuals?
   - Answer: one winning team, or the top 3 if competing individually. Each Robocar winner gets an
     Arduino UNO Q (4 GB) and a LEGO race car.
8. Does the day start at 9:30 AM or 10:00 AM?
   - Answer: doors and registration at 9:30 AM; building runs 10:00 AM to 4:00 PM (the listing
     says until 5:00).

## More, from the research

9. Which App Lab version and Python image do the boards run?
   - Why it matters: on images up to `bricks/0.13.1`, listing OpenCV in `requirements.txt` breaks
     the install.
   - Answer: App Lab 0.11.0. After its board update on Oct 24 the board runs arduino-app-cli
     0.14.0 and arduino-router 0.11.0, but the app's container is still
     `python-apps-base:0.13.1` (Python 3.13.15), so the OpenCV rule stands. Read on the board.
10. Is it the same black and white ball, white goal and taped field as the August Robot Soccer
    Cup, and will the guide's Edge Impulse project (1144501) get its labelled data?
    - Answer, on Oct 24: a different field, and yes to the data. In the late morning the project held the organizers' office
      pictures (321, labelled goal, robot and soccer_ball), and an organizer suggested phone
      pictures until a set from the room was ready. At 12:05 they replaced them with 353
      pictures from the room, labelled `soccerball` and `goal`; a few lacked their
      boxes, which the organizer said they would fix. The ball is a small white soccer ball
      with black patches, on carpet, and the goals are yellow cones. The field: gray carpet.
11. How do teams hand in the project: an App Lab export, a ZIP, a GitHub link or a form?
    - Why it matters: it decides where the submission README goes and what else to include.
    - Answer (the organizers, at 2:59 PM): one pull request to
      github.com/aaishikasb/uno-q-hackout-submissions adding only
      `10-24-neu/robocar-track/<github-username>.zip`, with the details in the ZIP's `app.yaml`,
      before 4:00 PM. Submitted at 3:45 PM as pull request 8.
12. Is the goal the gap between two yellow cones, and how far apart are they?
    - Why it matters: the organizers' pictures box each cone as its own goal, so aiming at the
      single most confident goal box would line the ball up with one cone, a post, instead of
      the gap. The code aims at the midpoint of the two most confident cone boxes instead.
    - Answer: measure the spacing yourself, the organizers said on Oct 24. They also confirmed
      the ball is white with black spots and the cones are yellow.
