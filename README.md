# Teler OpenAI Bridge

A reference integration between Teler and OpenAI Realtime API, based on Media Streaming over WebSockets. This project bridges Teler (telephony calls) with OpenAI Realtime API for live two-way conversational agents.

It handles:

Incoming audio from Teler (8kHz PCM16)

Upsampling to 24kHz for OpenAI

Sending audio chunks via WebSocket

Receiving AI-generated audio (24kHz PCM16)

Downsampling back to 8kHz for Teler

Streaming transcripts and responses in real-time

📞 Flow

Teler connects → streams 8kHz PCM audio chunks.

App upsamples to 24kHz → sends to OpenAI Realtime API.

OpenAI generates response audio (24kHz PCM16).

App downsamples to 8kHz → sends back to Teler.

Smooth playback ensured by audio buffering.

🔄 Call Flow

Teler → Bridge

Receives 8kHz PCM16 audio chunks from the telephony call.

Upsamples to 24kHz.

Sends to OpenAI via WebSocket (input_audio_buffer.append).

Bridge → OpenAI

Handles session creation (session.update).

Forwards audio in real-time.

OpenAI → Bridge

Streams AI-generated audio (response.output_audio.delta).

Buffers chunks for smooth playback.

Downsamples to 8kHz.

Bridge → Teler

Sends audio back into the live call.

Transcripts and AI text logs available in console.
