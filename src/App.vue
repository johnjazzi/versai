<template>
    <v-app>
      <v-container fluid class="flex flex-col justify-between h-screen">

        <div class="flex flex-col items-center justify-center flex-grow">
          <v-btn @click="toggleRecording" icon="mdi-microphone" class="mb-2">
            <v-icon>mdi-microphone</v-icon>
          </v-btn>
          <span v-if="isRecording">Recording...</span>
          <span v-else>Start Recording</span>
          current track: {{ currentTrack }}
          <v-progress-circular v-if="isRecording" :size="100" :width="10" :model-value="Math.round(volume)" color="green"></v-progress-circular>

        </div>
        <v-card class="overflow-y-auto flex-grow">
          <v-card-title>Transcript</v-card-title>
          <v-card-text>
            <div class="flex flex-col">
              <!-- Stub for messages -->
               {{ transcript }}
              <!-- <div class="m-1 p-2 rounded bg-green-200 self-end">User message here</div>
              <div class="m-1 p-2 rounded bg-gray-200 self-start">Response message here</div> -->
              <!-- Add more message stubs as needed -->
            </div>
          </v-card-text>
        </v-card>
        <!-- <v-textarea
          v-model="textInput"a
          label="Enter text to translate"
          @input="handleInput"
          class="mt-2"
        ></v-textarea> -->

        <v-snackbar v-for="alert in alerts" v-model="alert.visible" color="error">
          {{ alert.message }}
          <template v-slot:action="{ attrs }">
            <v-btn text v-bind="attrs" @click="alert.visible = false">Close</v-btn>
          </template>
        </v-snackbar>

      </v-container>
    </v-app>
  </template>
  
<script>

import { AutoTokenizer, AutoModelForSeq2SeqLM , pipeline} from '@huggingface/transformers';
  
  export default {
    data() {
      return {
        textInput: '',
        responses: [], // Array to store responses with timestamps
        socket: null, // WebSocket instance
        recorders: [null, null], // Two MediaRecorder instances
        currentTrack: 0, // 0 for Track 1, 1 for Track 2
        mediaRecorder: null,
        mediaRecorderInterval: 2500,
        trackSwitchInterval: 10000,
        isRecording: false,
        volume: 0, // Volume level (0-100)
        audioContext: null,
        analyser: null,
        microphone: null,    
        transcript: null,
        translatedTranscript: null,
        isResetPending: false,
        unsentChunks: [], // Buffer for failed chunks
        alerts : [], // Snackbar message
        translationModel: null,
        translationTokenizer: null,
        pipe: null,
        modelLoading: false,
        langMap: {
          'en': 'eng_Latn',
          'pt': 'por_Latn'
        },
      };
    },
    async mounted() {
      // this.pipe = await pipeline("translation", "Helsinki-NLP/opus-mt-en-roa")
      this.modelLoading = true
      console.log("loading model")
      const model = "Xenova/nllb-200-distilled-600M"
      this.pipe = await pipeline('translation', model);
      console.log("model loaded")
      console.log('testing model')
      console.log(await this.pipe("Hello, how are you?", {src_lang: "eng_Latn", tgt_lang: "por_Latn"}))
      this.modelLoading = false
    },
    methods: {
      async translate(text, sourceLang, targetLang) {
        return this.pipe(text, {src_lang: this.langMap[sourceLang], tgt_lang: this.langMap[targetLang]}); 
      },

      async toggleRecording() {
        if (this.isRecording) {
          this.stopRecording();
        } else {
          await this.startRecording();
        }
      },
      async startRecording() {
        if (this.isRecording) return;
        this.startWebSocket()

        console.log('start recording')
        try {
          this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });

          this.recorders[0] = await this.createMediaRecorder(0);
          this.recorders[1] = await this.createMediaRecorder(1);
          this.currentTrack = 0;
          this.recorders[0].start(this.mediaRecorderInterval);
          this.isRecording = true;

          // Set up audio context, gain node, and analyser
          this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
          this.gainNode = this.audioContext.createGain(); // Create a gain node
          this.gainNode.gain.value = 128; // Set gain value to amplify the audio (2x amplification)
          this.analyser = this.audioContext.createAnalyser();
          this.microphone = this.audioContext.createMediaStreamSource(this.mediaStream);
          this.microphone.connect(this.gainNode);
          this.gainNode.connect(this.analyser);
          this.analyser.fftSize = 2048;

          const dataArray = new Uint8Array(this.analyser.frequencyBinCount);

          const updateVolume = () => {
            this.analyser.getByteFrequencyData(dataArray);
            const sum = dataArray.reduce((a, b) => a + b, 0);
            this.volume = (sum / dataArray.length) * 100 / 255; // Normalize to 0-100
            if (this.isRecording) {
              requestAnimationFrame(updateVolume);
            }
          };

          setInterval(() => {
              if (this.isRecording) {
                this.switchTrack()
              }
            }, this.trackSwitchInterval // 10 seconds`
          )

          this.isRecording = true;
        } catch (error) {
          console.error('Error accessing microphone:', error);
        }
      },
      async switchTrack() {
        const prevTrack = this.currentTrack;
        const nextTrack = (this.currentTrack + 1) % 2;
        console.log("switching tracks from", prevTrack, "to", nextTrack)
        this.recorders[nextTrack].start(this.mediaRecorderInterval);
        this.recorders[prevTrack].stop();
        this.recorders[prevTrack] = null
        // TODO: its really going to depend when I send the reset. if I send before the previous 
        this.isResetPending = true
        this.recorders[prevTrack] = await this.createMediaRecorder(prevTrack);
        this.currentTrack = nextTrack;
      },
      async createMediaRecorder(trackIndex) {
        const recorder = new MediaRecorder(this.mediaStream, { mimeType: "audio/webm" });

        recorder.ondataavailable = async (event) => {
            if (this.isRecording) {
                const audioBlob = new Blob([event.data], { type: 'audio/webm' });
                console.log(audioBlob, `Track ${trackIndex}`)
                await this.sendAudio(audioBlob);
                if (this.isResetPending) {
                  this.sendReset()
                  this.isResetPending = false
                }
            }
          };

        recorder.onstop = () => {
          console.log(`Track ${trackIndex} stopped.`);
        };

        return recorder;
      },
      stopRecording() {
        if (!this.isRecording) return;
        this.isRecording = false;

        this.recorders = [null, null] // reset the recorder tracks

        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
          this.socket.close(); // Close the WebSocket connection if it's open
        }
      },
      async sendAudio(audioBlob) {
        await this.checkWSReady()
        
        if (this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(audioBlob);
        } else {
            console.error('WebSocket is not in OPEN state');
        }
      },
      async sendReset() {
        console.log("sending reset")
        if (this.socket.readyState === WebSocket.OPEN) {
          this.socket.send(new Blob([JSON.stringify({ reset: true })]));
        } else {
            console.error('WebSocket is not in OPEN state');
        }
      },
      async startWebSocket() {
        try {
          this.socket = new WebSocket('ws://localhost:8000/audio'); // Connect to WebSocket server
        } catch (error) {
          console.error('Error connecting to WebSocket:', error);
          this.alerts.push({
            Message: error.message,
            visible: true
          })
        }
        this.socket.onopen = () => {
            console.log('WebSocket connection established');
            // Start audio recording logic here
          };
        this.socket.onmessage = async (event) => {
          const message = JSON.parse(event.data).message;
          const lang = JSON.parse(event.data).info
          this.transcript = message;
          console.log(event.data);

          if (lang === "pt") {
            this.translatedTranscript = await this.translate(message, lang, "en")
          } else {
            this.translatedTranscript = await this.translate(message, lang, "pt")
          }

          console.log(this.translatedTranscript)

        };
        this.socket.onerror = (error) => {
          console.error('WebSocket error:', error);
        };
        this.socket.onclose = () => {
          console.log('WebSocket connection closed');
          this.socket = null;
        };
      },
      async checkWSReady() {
        // todo: need to figure out how to handle unsent chunks here
        if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
            await this.startWebSocket();
            // Wait for connection to be established
            await new Promise((resolve, reject) => {
                const timeout = setTimeout(() => reject(new Error('WebSocket connection timeout')), 500);
                this.socket.onopen = () => {
                    clearTimeout(timeout);
                    resolve();
                };
            });
        }
      },
    },
  };
  </script>
  
  <style>
  .volume-bar {
    height: 10px;
    background-color: green;
    transition: width 0.1s;
  }
  </style>