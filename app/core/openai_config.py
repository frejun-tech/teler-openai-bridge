openai_configurations = {
  "type": "session.update",
  "session": {
    "type": "realtime",
    "model": "gpt-realtime-2.1",

    "audio": {
      "input": {
        "format": {
          "type": "audio/pcm",
          "rate": 24000
        },

        "noise_reduction": {
          "type": "near_field"
        },

        "turn_detection": {
          "type": "server_vad",
          "threshold": 0.55,
          "prefix_padding_ms": 300,
          "silence_duration_ms": 600,
          "create_response": True,
          "interrupt_response": True
        },

        "transcription": {
          "model": "gpt-transcribe"
        }
      },

      "output": {
        "format": {
          "type": "audio/pcm",
          "rate": 24000
        }
      }
    },

    "output_modalities": ["audio"]
  }
}

initial_instruction = {
  "type": "conversation.item.create",
  "item": {
      "type": "message",
      "role": "user",
      "content": [
          {
              "type": "input_text",
              "text": "Say hello and greet the customer in one short sentence.",
          }
      ],
  },
}