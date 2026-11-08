"""T07 ingest: turn source media into what the editor needs.

probe.py reads Source fields off a media file with ffprobe. transcribe/ maps a
provider's transcript into the T02 Word/Transcript model (or imports a JSON/SRT/VTT
file someone already has). proxy.py and peaks.py build the editor's playback proxy and
waveform peaks. worker.py exposes all three as ``python -m post_core.ingest.worker``
subprocesses speaking the T03 ``##POST`` contract.
"""
