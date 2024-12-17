<template>
    <v-app>
      <v-container fluid class="flex flex-col justify-between h-screen">

        <div class="flex flex-col items-center justify-center flex-grow">
          <v-btn @click="loadPipe" class="mb-2" v-if="!transcriber.initialized">Load Pipe</v-btn>
          <v-btn @click="toggleRecording" icon="mdi-microphone" class="mb-2" :disabled="!transcriber.initialized">
            <v-icon>mdi-microphone</v-icon>
          </v-btn>
          <span v-if="isRecording">Recording...</span>
          <span v-else>Start Recording</span>
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
          <v-card-title>Translation</v-card-title>
          <v-card-text>
            <div class="flex flex-col">
              <!-- Stub for messages -->
               {{ translation }}
              <!-- <div class="m-1 p-2 rounded bg-green-200 self-end">User message here</div>
              <div class="m-1 p-2 rounded bg-gray-200 self-start">Response message here</div> -->
              <!-- Add more message stubs as needed -->
            </div>
          </v-card-text>
        </v-card>



      </v-container>

      <v-snackbar v-for="alert in alerts" v-model="alert.visible" color="error">
          {{ alert.message }}
          <template v-slot:action="{ attrs }">
            <v-btn text v-bind="attrs" @click="alert.visible = false">Close</v-btn>
          </template>
        </v-snackbar>

      <v-dialog v-model="loadingPipe" color="info">
          <v-card>
            <v-card-title>Loading Pipe</v-card-title>
            <v-card-text>
              <div v-for="status in loadingStatus" :key="status.file">
                <Progress :text="`Loading ${status.file}`" :percentage="status.percentage" />
              </div>
            </v-card-text>
          </v-card>

        </v-dialog>
    </v-app>
  </template>
  
<script>

// son of a bitch: https://github.com/xenova/whisper-web/

// npm i @huggingface/transformers
import Progress from './components/Progress.vue'; // Import the Progress component


import {
  AutoTokenizer,
  AutoProcessor,
  WhisperForConditionalGeneration,
  TextStreamer,
  full,
} from "@huggingface/transformers";
// Allocate pipeline


  
  export default {
    components: {
      Progress
    },
    data() {
      return {
        configs: {
          model: 'onnx-community/whisper-base',
          mediaRecorderInterval: 5000,
          trackSwitchInterval: 5000,
          mimeType: "audio/mp4",
          IS_WEBGPU_AVAILABLE:  !!navigator.gpu,
          WHISPER_SAMPLING_RATE: 16_000, // 16kHz
          MAX_AUDIO_LENGTH: 30, // 300 seconds
          MAX_SAMPLES : 30*16000,
          MAX_NEW_TOKENS: 64,
        },
        textInput: '',
        responses: [], // Array to store responses with timestamps
        socket: null, // WebSocket instance
        recorder: null,
        mediaRecorder: null,
        isRecording: false,
        volume: 0, // Volume level (0-100)
        audioContext: null,
        analyser: null,
        microphone: null,    
        audioBuffer: [],

        transcript: null,
        translation: null,
        alerts : [], // Snackbar message

        loadingPipe: false,
        loadingStatus: [],
        transcriber: {
          isProcessing: false,
          tokenizer: null,
          processor: null,
          model: null,
          streamer: null,
          initialized: false,
        },
      };
    },

    methods: {
      async loadPipe() {
        console.log('loading pipe');
        this.loadingPipe = true;
        this.loadingStatus = []; // Reset loading status

        this.transcriber.tokenizer = await AutoTokenizer.from_pretrained(this.configs.model, { progress_callback: (progress) => this.handleProgress(progress) });
        this.transcriber.processor = await AutoProcessor.from_pretrained(this.configs.model, { progress_callback: (progress) => this.handleProgress(progress) });
        this.transcriber.model = await WhisperForConditionalGeneration.from_pretrained(
          this.configs.model, { 
            dtype: {
              encoder_model: "fp32",
              decoder_model_merged: "q4",
            },
            device: "webgpu",
            progress_callback: (progress) => this.handleProgress(progress) });
        this.transcriber.initialized = true;

        console.log('warming model')
        await this.transcriber.model.generate({
          input_features: full([1, 80, 3000], 0.0),
          max_new_tokens: 1,
        })
        console.log('model warmed')

        console.log('pipe loaded');
        this.loadingStatus = []; // Clear progress after loading
        this.loadingPipe = false;
      },

      async generate({audio,language = 'en'}) {
        if (this.transcriber.isProcessing) return;
        this.transcriber.isProcessing = true;

        let startTime;
        let numTokens = 0;
        let tps;

        const token_callback_function = () => {
          startTime ??= performance.now();
          if (numTokens++ > 0) {
            tps = (numTokens / (performance.now() - startTime)) * 1000;
          }
        };

        const callback_function = (output) => {
          self.postMessage({
            status: "update",
            output,
            tps,
            numTokens,
          });
        };

        const streamer = new TextStreamer(this.transcriber.tokenizer, {
          skip_prompt: true,
          skip_special_tokens: true,
          callback_function,
          token_callback_function,
        });

        const inputs = await this.transcriber.processor(audio)
        const outputs = await this.transcriber.model.generate({
          ...inputs,
          max_new_tokens: this.configs.MAX_NEW_TOKENS,
          language,
          streamer,
        });

        const decoded = this.transcriber.tokenizer.batch_decode(outputs, {
          skip_special_tokens: true,
        });

        console.log('outputs', decoded)
        this.transcriber.isProcessing = false;
        return decoded
      },

      handleProgress(progress) {
        let fileStatus = this.loadingStatus.find(status => status.file === progress.file);
            if (!fileStatus) {
              fileStatus = { file: progress.file, percentage: 0 };
              this.loadingStatus.push(fileStatus);
            }
            // Update the percentage for the file
            if (progress && progress.progress !== undefined) {
              fileStatus.percentage = progress.progress ; // Convert to percentage
            } 
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
        if (!this.transcriber.initialized) return;

        console.log('start recording')
        try {
          this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
          this.recorder = new MediaRecorder(this.mediaStream);
          this.audioContext = new AudioContext({sampleRate: this.configs.WHISPER_SAMPLING_RATE});

          this.recorder.onstart = () => {
            this.audioBuffer = []
            this.isRecording = true;
          }

          this.recorder.onstop = () => {
            this.isRecording = false;
          }

          this.recorder.ondataavailable = async (event) => {
            console.log('ondataavailable', event.data.size)
            if (event.data.size > 0) {
              this.audioBuffer = [ ...this.audioBuffer, event.data ]
            } else {
              setTimeout(() => {
                this.recorder.requestData()
              }, 25);
            }
          };

          this.recorder.start(5000);
          this.isRecording = true;

          // Set up audio context, gain node, and analyser

          this.gainNode = this.audioContext.createGain(); // Create a gain node
          this.gainNode.gain.value = 64; // Set gain value to amplify the audio (2x amplification)
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

          updateVolume()

        } catch (error) {
          console.error('Error starting recording:', error);
        }
      },

      stopRecording() {
        this.recorder.stop();
        this.isRecording = false;
        this.audioBuffer = [];
        this.audioContext.close();
        this.analyser = null;
        this.microphone = null;
        this.gainNode = null;
        this.mediaStream = null;
        this.recorder = null;
      }

    },

    watch: {
      audioBuffer: async function() {
        if (this.audioBuffer != null && this.audioBuffer.length > 0) {

          const blob = new Blob(this.audioBuffer, { type: this.recorder.mimeType });
          const fileReader = new FileReader();

          fileReader.onload = async () => {
            const arrayBuffer = fileReader.result;
            const decoded = await this.audioContext.decodeAudioData(arrayBuffer);
            let audio = decoded.getChannelData(0);
            if (audio.length > this.configs.MAX_SAMPLES) {
              audio = audio.slice(-this.configs.MAX_SAMPLES);
            }

            const transcript = await this.generate({audio});
            this.transcript = transcript;
          }

          fileReader.readAsArrayBuffer(blob);
        }
      }
    }


  };
  </script>
  
  <style>
  .volume-bar {
    height: 10px;
    background-color: green;
    transition: width 0.1s;
  }
  </style>