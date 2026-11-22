English | [简体中文](DEVLOG_ZH.md)

# V1.8.2 · Story transitions and choice timers

During a fade, a button can remain in the reuse pool after the video layer stops accepting input. The previous timer override could pause the whole video on a silent black frame. Turning it off restored playback in the reported scene.

The revised check looks at the current clip, fade state, visible countdown and whether an answer belonging to that clip can still be clicked. It holds a genuine timed choice in its final half-second and releases the hold when the choice disappears. Automatic transitions and untimed dialogue play through.

The public build passed 173 offline checks. With the same timer implementation in the installed build, the player repeated the affected transition with unlimited choice time enabled and confirmed normal playback. All 252 files in the complete archive were checked after extraction. The public source rebuilt the archived plugin byte-for-byte with the matching local inputs.

[Project overview](README.md) · [Release](https://github.com/Haaaaa96/single-player-trainers/releases/tag/rise-alone-v1.8.2)
