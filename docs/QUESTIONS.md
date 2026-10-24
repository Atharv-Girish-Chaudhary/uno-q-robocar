# Questions for the organizers

The office hours (Tue Oct 20, 2:00 PM PT, with the two judges) have passed. The event page and
the host's email of Oct 21 answer questions 7 and 8. Ask the rest at check-in, or ask the
Qualcomm mentors on site.

1. What are the "agreed conditions" for ball detection: ball color, lighting, distances,
   distractor objects?
   - Why it matters: it sets the detector's color and what to test. The guide's labels say
     "soccerball", and the August event used a black and white soccer ball.
   - Answer: open.
2. How is the final run set up: fixed or randomized ball and goal positions, how many attempts,
   any time limit?
   - Why it matters: it sets `run_time_limit_s` and `max_pushes`, and decides how much the goal
     finder matters.
   - Answer: open.
3. The event page says the robocar that scores first wins, but the rubric has no speed criterion.
   Does speed count?
   - Why it matters: it decides how long and fast the pulses should be once the run is reliable.
   - Answer: open.
4. Can we bring a detector prepared in advance, or must everything be built on the day?
   - Why it matters: it decides whether the prep code and a pre-trained model can be used as
     they are.
   - Answer: open.
5. Which Wi-Fi network should the boards use for their first run, and does it need a login page?
   - Why it matters: the first run downloads and compiles the sketch's Arduino libraries, and a
     board without a screen can't get past a login page.
   - Answer: open. The venue has Wi-Fi; a phone hotspot is the fallback.
6. Arcade: does a RetroArch game count as original if we wrote it ourselves?
   - Why it matters: the Arcade rubric scores originality (20 points). Not this track, but worth
     knowing.
   - Answer: open.
7. How do prizes work for teams versus individuals?
   - Answer: one winning team, or the top 3 if competing individually. Each Robocar winner gets a
     LEGO APXGP Team Race Car (F1) and an UNO Q 4GB. Source: the host's email.
8. Does the day start at 9:30 AM or 10:00 AM?
   - Answer: doors and registration at 9:30 AM; building runs 10:00 AM to 4:00 PM (the listing
     says until 5:00). Source: the host's email of Oct 21.

## More, from the research

9. Which App Lab version and Python image do the boards run?
   - Why it matters: on images up to `bricks/0.13.1`, listing OpenCV in `requirements.txt` breaks
     the install.
10. Is it the same black and white ball, white goal and taped field as the August Robot Soccer
    Cup, and will the guide's Edge Impulse project (1144501) get its labelled data?
11. How do teams hand in the project: an App Lab export, a ZIP, a GitHub link or a form?
    - Why it matters: it decides where the submission README goes and what else to include.
    - Answer: open. Neither the event page nor the guide says.
