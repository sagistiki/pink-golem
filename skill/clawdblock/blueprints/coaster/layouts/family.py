"""family.py — a small family coaster: a 22-block lift, one drop, a climbing turnaround, a camel hump, a small
helix, no loop. About 45 × 110 blocks and 25 high. Use it with
    python3 track.py --layout layouts/family.py --plot /tmp/family      (check it)
    python3 build.py --at X,Y,Z --facing east --layout layouts/family.py --title "LITTLE DRAGON"
The rules every layout follows are in README.md ("Your own layout").
"""
import math


def layout(t):
    B = t.y0                                             # the station track height; every y1 below is B + something
    t.seg(20, tag="station")                             # flat and straight: the platform is built along it
    t.seg(15.7, turn=90, tag="tyres")                    # right turn, r 10
    t.seg(6, y1=B + 2.0, m1=0.8, tag="lift")
    t.seg(24, y1=B + 21.0, m1=0.8, tag="lift")           # the chain lift, 39°
    t.seg(6, y1=B + 22.0, m1=-0.6, tag="lift")           # crest
    t.seg(20, y1=B + 4.5, m1=-1.0)                       # the drop
    t.seg(16, y1=B + 0.5, m1=0.0)                        # a long pull-out: no dip below the station, under 5 G
    r = (t.along() + 6) / 2                              # a 180 that lands the way back 6 behind the station start
    t.seg(r * math.pi / 2, turn=90, y1=B + 7.0, m1=0.0)
    t.seg(r * math.pi / 2, turn=90, y1=B + 3.0, m1=-0.2)
    t.seg(12, y1=B + 0.5, m1=0.0)
    t.seg(16, y1=B + 4.5, m1=0.0, tag="air")             # camel hump
    t.seg(16, y1=B + 0.5, m1=0.0)
    t.seg(37.7, turn=360, y1=B + 2.5, m1=0.0, tag="helix")   # a small rising helix, r 6
    t.seg(10, y1=B + 0.5, m1=0.0)
    rest = t.side() - 6                                  # the straight left before the last turn
    t.seg(rest - 10, y1=B + 0.5, tag="brakes")
    t.seg(10, y1=B, m1=0.0, tag="brakes")
    t.seg(6 * math.pi / 2, turn=90, y1=B, tag="tyres")   # r 6 into the station
    return t
