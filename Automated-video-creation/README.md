# Automated video creation

Generates a vertical short video with a random topic every day, fully on GitHub Actions (free).

Gemini (topic + script) -> edge-tts (voice) -> Pixabay (footage) -> FFmpeg (video + captions)

## Setup
1. Repo > Settings > Secrets and variables > Actions > New repository secret:
   - `GEMINI_API_KEY` (from aistudio.google.com/apikey)
   - `PIXABAY_API_KEY` (free, from pixabay.com/api/docs/)
2. Actions tab > "Generate daily video" > Run workflow.
3. When it finishes, download the video from the run's Artifacts section.

It then runs automatically every day at 04:30 UTC. `history.json` stores past topics so none repeat.
