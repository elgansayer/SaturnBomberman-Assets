# Observed original RGB source pattern

USA MK-81070 V1.003, accepted checkpoint frame3000, command byte96.
320x160 source-oriented RGB555 pattern. Subject/source resource is unidentified;
this is not a player spritesheet, animation sequence or final composited frame.

Two exports matched. Independent PNG parsing checked all51200 pixels and recovered
every native word; a changed colour bit was detected. Input graphics arrays matched
a separate direct memory read from the same accepted core. See provenance.json.
No raw save state, full VRAM/CRAM, BIOS, disc or credentials are stored here.

Regenerate privately using Neptune tools/saturn_lab/state_graphics.py and then
export_vdp1.py --vram CAPTURE/vram.bin --capture CAPTURE/capture.json
--command-offset 0x60 --output NEW_DIRECTORY. Pin source identities and preserve
word order/context exactly as recorded. Full acquisition recipe/evidence is in
Neptune PR528; pixel proof is in the linked issue529.

Original Hudson/SEGA content. This private research publication grants no public
redistribution permission and does not change the Neptune engine licence.
