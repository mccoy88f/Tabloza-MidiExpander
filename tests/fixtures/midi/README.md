# Fixture MIDI di test

| File | Descrizione |
|------|-------------|
| `c-major-scale.mid` | Scala di Do maggiore (8 note), formato 0, 480 PPQ — generato per test automatici |

## Riproduzione locale (Linux / Raspberry Pi)

```bash
# Verso FluidSynth (porta ALSA tipica Tabloza)
aplaymidi -p 129:0 tests/fixtures/midi/c-major-scale.mid

# Oppure via FluidSynth CLI
fluidsynth -a alsa -m alsa_seq /usr/share/sounds/sf2/FluidR3_GM.sf2 \
  tests/fixtures/midi/c-major-scale.mid
```

Su Tabloza il file viene copiato in `/opt/tabloza/tests/fixtures/midi/` dopo `tabloza-update`.
