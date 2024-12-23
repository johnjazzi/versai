<template>
    <v-app>

      
      <v-container fluid class="flex flex-col justify-between">
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
          <v-card-title v-if="translation">Translation</v-card-title>
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


        <v-card>
          <div class="flex flex-col items-center justify-center flex-grow">
          <div class="flex space-x-2 m-2 justify-center">
            <div class="flex flex-col items-center w-1/2">
              <v-btn @click="toggleRecording(this.languages.lang1)" icon="mdi-microphone" :disabled="!transcriber.initialized">
                <v-icon>mdi-microphone</v-icon>
              </v-btn>
              <v-select
                v-model="languages.lang1"
                :items="languageOptions"
                item-title="name"
                item-value="code"
                label="Select Language 1"
                class="mt-2"
                density="compact"
                disabled
              ></v-select>
            </div>
            <div class="flex flex-col items-center w-1/2">
              <v-btn @click="toggleRecording(this.languages.lang2)" icon="mdi-microphone" :disabled="!transcriber.initialized">
                <v-icon>mdi-microphone</v-icon>
              </v-btn>
              <v-select
                v-model="languages.lang2"
                :items="languageOptions"
                item-title="name"
                item-value="code"
                label="Select Language 2"
                class="mt-2"
                density="compact"
              ></v-select>
            </div>
          </div>
          <span v-if="isRecording">Recording...</span>
          <span v-else>click microphone to record</span>
          <v-progress-circular v-if="isRecording" :size="100" :width="10" :model-value="Math.round(volume)" color="green"></v-progress-circular>
        </div>
        </v-card> 

      </v-container>

    
      <v-snackbar v-for="alert in alerts" v-model="alert.visible" color="error">
          {{ alert.message }}
          <template v-slot:action="{ attrs }">
            <v-btn text v-bind="attrs" @click="alert.visible = false">Close</v-btn>
          </template>
        </v-snackbar>

      <v-dialog v-model="transcriberInitialized" color="info">
          <v-card>
            
            <v-card-title>Loading Models</v-card-title>
            <v-card-text>
              <v-alert type="error" v-if="!configs.IS_WEBGPU_AVAILABLE">WebGPU is not available. Enable WebGPU in your browser settings.</v-alert>
              <div v-if="!loadingPipe" class="flex flex-col items-center justify-center flex-grow">
                <v-btn @click="loadPipe" class="m-2" color="primary">Load Model</v-btn>
                <div >Model will be downloaded to browser cache. You only need to do this once.</div>
              </div>
              
                <div v-for="status in loadingStatus" :key="status.file">
                  <Progress :text="`${status.file}`" :percentage="status.percentage" :total="status.total"  />
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
import { env } from '@xenova/transformers';


import {
  AutoTokenizer,
  AutoProcessor,
  WhisperForConditionalGeneration,
  AutoModelForAudioFrameClassification,
  TextStreamer,
  full,
  pipeline,
  AutoModelForSeq2SeqLM,
  WhisperProcessor
} from "@huggingface/transformers";
// Allocate pipeline

import languageData from './languages.json';
  
export default {
    components: {
      Progress
    },
    data() {
      return {
        showWebGPUWarning: true,
        configs: {
          transcriber_model: 'onnx-community/whisper-base',
          segmenter_model: 'onnx-community/pyannote-segmentation-3.0',
          segmenter: false, // use segmenter
          translator: true, // use translator
          mediaRecorderInterval: 5000,
          trackSwitchInterval: 5000,
          mimeType: "audio/mp4",
          IS_WEBGPU_AVAILABLE:  !!navigator.gpu,
          WHISPER_SAMPLING_RATE: 16_000, // 16kHz
          MAX_AUDIO_LENGTH: 30, // 300 seconds
          MAX_SAMPLES : 30*16000,
          MAX_NEW_TOKENS: 64,
          device: "webgpu",
        },
        languages: {
          lang1: 'en',
          lang2: 'pt_BR',
        },
        languageOptions: languageData.romance_languages,
        currentLanguage: 'en',
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
        segmenter: {
          isProcessing: false,
          processor: null,
          model: null,
          initialized: false,
        },
        translator: {
          ro_to_eng_pipe: null,
          eng_to_ro_pipe: null,
          isProcessing: false,
          initialized: false,
        },
      };
    },

    computed: {
      oppositeLanguage() {
        return this.currentLanguage === 'en' ? this.languages.lang2 : 'en';
      }, 
      transcriberInitialized() {
        return !this.transcriber.initialized;
      }
    },

    methods: {
      async loadTranscriber() {
        console.log('loading transcriber')
        this.transcriber.tokenizer = await AutoTokenizer.from_pretrained(this.configs.transcriber_model, { progress_callback: (progress) => this.handleProgress(progress) });
        this.transcriber.processor = await WhisperProcessor.from_pretrained(this.configs.transcriber_model, { progress_callback: (progress) => this.handleProgress(progress) });
        this.transcriber.model = await WhisperForConditionalGeneration.from_pretrained(
            this.configs.transcriber_model, { 
              dtype: {
                encoder_model: "fp32",
                decoder_model_merged: "q4",
              },
              device: this.configs.device,
              progress_callback: (progress) => this.handleProgress(progress) });
        this.transcriber.initialized = true;

        this.transcriber.model.save_pretrained('/model/whisper-base')
        this.transcriber.tokenizer.save_pretrained('/model/whisper-base')
        this.transcriber.processor.save_pretrained('/model/whisper-base')

        console.log('warming transcriber')
        await this.transcriber.model.generate({
            input_features: full([1, 80, 3000], 0.0),
            max_new_tokens: 1,
            language: 'Japanese',
          })
          console.log('transcriber loaded andwarmed')
      }, 

      async loadSegmenter() {
        console.log('loading segmenter')
        this.segmenter.processor = await AutoProcessor.from_pretrained(this.configs.segmenter_model, { progress_callback: (progress) => this.handleProgress(progress) });
        this.segmenter.model = await AutoModelForAudioFrameClassification.from_pretrained(this.configs.segmenter_model, { 
            dtype: "fp32",
            device: "wasm",
            progress_callback: (progress) => this.handleProgress(progress) });
        this.segmenter.initialized = true;
        console.log('segmenter loaded')
      },

      async loadTranslator() {
        
        console.log('loading translator')
        this.translator.ro_to_eng_pipe = await pipeline('translation', 'Xenova/opus-mt-ROMANCE-en', { device: this.configs.device , progress_callback: (progress) => this.handleProgress(progress) });
        this.translator.eng_to_ro_pipe = await pipeline('translation', 'Xenova/opus-mt-en-ROMANCE', { device: this.configs.device , progress_callback: (progress) => this.handleProgress(progress) });

        console.log('warming translator')
        console.log(await this.translator.eng_to_ro_pipe(" >>pt_BR<< Hello world!"))

        console.log(await this.translator.ro_to_eng_pipe("Oi tudo bem?"))

        console.log('translator loaded')
        this.translator.initialized = true;
      },

      async loadPipe() {;
        this.loadingPipe = true;
        this.loadingStatus = []; // Reset loading status

        try {

          await this.loadTranscriber();

          if (this.configs.segmenter) {
            await this.loadSegmenter();
          }

          if (this.configs.translator) {
            await this.loadTranslator();
          }

        } catch (error) {
          this.loadingStatus = []; // Clear progress after loading
          this.loadingPipe = false;
          console.error('Error loading pipe:', error);
          this.alerts.push({
            message: error.message,
            visible: true,
          });
        }

        this.loadingStatus = []; // Clear progress after loading
        this.loadingPipe = false;
      },

      async segment({audio}) {
        if (this.segmenter.isProcessing || !this.segmenter.initialized) return;
        this.segmenter.isProcessing = true;

        const inputs = await this.segmenter.processor(audio)
        const { logits } = await this.segmenter.model(inputs);
        const segments = this.segmenter.processor.post_process_speaker_diarization(logits, audio.length)[0];

        for (const segment of segments) {
            segment.label = this.segmenter.model.config.id2label[segment.id];
        }

        this.segmenter.isProcessing = false;
        return segments;
      },

      async transcribe({audio,language_from = 'en'}) {
        if (this.transcriber.isProcessing) return;
        this.transcriber.isProcessing = true;

        // translate to language NOT WORKING
        let forced_decoder_ids = null;
        // if (language_to != null) {
        //   forced_decoder_ids = WhisperProcessor.get_decoder_prompt_ids(language_from, "translate")
        // } 

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
          language: language_from.split('_')[0],
          streamer,
          ...(forced_decoder_ids ? { forced_decoder_ids } : {}),
        });

        const decoded = this.transcriber.tokenizer.batch_decode(outputs, {
          skip_special_tokens: true,
        });

        console.log('outputs', decoded)
        this.transcriber.isProcessing = false;
        return decoded
      },

      async translate({text, source_language = 'en', target_language = 'pt_BR'}) {

        if (this.translator.isProcessing || !this.translator.initialized) return;
        this.translator.isProcessing = true;

        console.log('translating', text, source_language, target_language)

        let translated;
        if (source_language == 'en') {
          translated  = await this.translator.eng_to_ro_pipe(` >>${target_language}<< ${text}`)
        } else {
          translated = await this.translator.ro_to_eng_pipe(`${text}`)
        }

        this.translator.isProcessing = false;
        return translated
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
      async toggleRecording(language) {
        if (this.isRecording) {
          this.stopRecording();
        } else {
          await this.startRecording();
          this.currentLanguage = language;
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

          this.recorder.start(3000);
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
            if (this.isRecording) {
              this.analyser.getByteFrequencyData(dataArray);
              const sum = dataArray.reduce((a, b) => a + b, 0);
              this.volume = (sum / dataArray.length) * 100 / 255; // Normalize to 0-100
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
      }

    },

    watch: {
      audioBuffer: async function() {
        if (this.audioBuffer != null && this.audioBuffer.length > 0 ) {

          const blob = new Blob(this.audioBuffer, { type: this.recorder.mimeType });
          const fileReader = new FileReader();

          fileReader.onload = async () => {
            const arrayBuffer = fileReader.result;
            const decoded = await this.audioContext.decodeAudioData(arrayBuffer);
            let audio = decoded.getChannelData(0);
            if (audio.length > this.configs.MAX_SAMPLES) {
              audio = audio.slice(-this.configs.MAX_SAMPLES);
            }

            if (this.segmenter.initialized) {
              const segments = await this.segment({audio});
              console.log('segments', segments)
            }

            const transcript = await this.transcribe({audio, language_from: this.currentLanguage});
            this.transcript = transcript[0];
            if ( this.translator.initialized) {
              const translation = await this.translate({text: transcript[0], source_language: this.currentLanguage, target_language: this.oppositeLanguage});
              console.log('translation', translation)
              this.translation = translation;
            }
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