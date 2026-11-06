"""Speed, time left and throttling for a download's progress line (launcher update and game install/update)."""
import time

EVERY = 0.25            # seconds: the screen is refreshed at most four times a second, and chunks come faster
WINDOW = 5.0            # the speed is the average of the last seconds


class Meter:
    def __init__(self, now=None):
        self.now = now or time.time
        self.samples = []
        self.step = None
        self.stamp = 0.0

    def update(self, step, done, total):
        """-> dict(step, done, total, speed, left), or None when this report is too soon after the last one of the
        same step (a step's first report and the one that completes it always pass)."""
        now = self.now()
        done, total = int(done or 0), int(total or 0)
        if self.step != step:
            self.samples.clear()
        elif now - self.stamp < EVERY and not (total and done >= total):
            return None
        self.step, self.stamp = step, now
        self.samples.append((now, done))
        while len(self.samples) > 2 and now - self.samples[0][0] > WINDOW:
            self.samples.pop(0)
        speed = 0.0
        if len(self.samples) > 1 and self.samples[-1][0] > self.samples[0][0]:
            speed = max(0.0, (self.samples[-1][1] - self.samples[0][1]) / (self.samples[-1][0] - self.samples[0][0]))
        left = int((total - done) / speed) if speed > 0 and total > done else 0
        return dict(step=step, done=done, total=total, speed=int(speed), left=left)
