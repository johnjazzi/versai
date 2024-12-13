<template>
    <v-app>
      <v-container fluid class="flex flex-col justify-between h-screen">

        <div class="flex flex-col items-center justify-center flex-grow">
          <v-btn @click="toggleRecording" icon="mdi-microphone" class="mb-2">
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
        </v-card>
        <!-- <v-textarea
          v-model="textInput"a
          label="Enter text to translate"
          @input="handleInput"
          class="mt-2"
        ></v-textarea> -->

      </v-container>
    </v-app>
  </template>
  
<script>
  
  export default {
    data() {
      return {
        textInput: '',
        responses: [], // Array to store responses with timestamps
        socket: null, // WebSocket instance
        mediaRecorder: null,
        isRecording: false,
        volume: 0, // Volume level (0-100)
        audioContext: null,
        analyser: null,
        microphone: null,    
        transcript: null    
      };
    },
    methods: {
      async handleInput() {
        const text = this.textInput;
  
        if (text) {
          const requestTime = new Date(); // Timestamp for request
          try {
            const response = await fetch('http://localhost:8000/', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({ text }),
            });
            const data = await response.json();
            const responseTime = new Date(); // Timestamp for response
  
            // Store response and timestamps in the array with milliseconds
            this.responses.push({
              request: { text, time: requestTime.getTime() },
              response: { message: data.message || data.error, time: responseTime.getTime() },
            });
            console.log(data.message)
          } catch (error) {
            this.$refs.translationOutput.innerText = 'Error: ' + error.message;
          }
        } else {
          this.responses = [];
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
        console.log('start recording')
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          this.mediaRecorder = new MediaRecorder(stream, { 
            mimeType: 'audio/webm' ,
            audioBitsPerSecond: 128000
        });
          
          // Set up audio context, gain node, and analyser
          this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
          this.gainNode = this.audioContext.createGain(); // Create a gain node
          this.gainNode.gain.value = 128; // Set gain value to amplify the audio (2x amplification)

          this.analyser = this.audioContext.createAnalyser();
          this.microphone = this.audioContext.createMediaStreamSource(stream);
          
          // Connect nodes: microphone -> gainNode -> analyser
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

          // Stream audio data as it becomes available
          this.mediaRecorder.ondataavailable = async (event) => {
            if (this.isRecording) {
                const audioBlob = new Blob([event.data], { type: 'audio/webm' });
                console.log(audioBlob)
                await this.sendAudio(audioBlob);
            }
          };

          this.mediaRecorder.onstart = () => {
            updateVolume(); // Start updating the volume
          };

          setInterval(() => {
              if (this.isRecording) {
                this.mediaRecorder.stop()
                this.mediaRecorder.start(2000)
                console.log('resetting')
                this.sendReset()
              }
            }, 10000
          )

          this.mediaRecorder.onstop = () => {
            //this.audioContext.close(); // Close the audio context
          };

          this.mediaRecorder.start(2000); // Start recording with a timeslice of 100ms
          this.isRecording = true;
        } catch (error) {
          console.error('Error accessing microphone:', error);
        }
      },
      stopRecording() {
        this.mediaRecorder.stop();
        this.isRecording = false;
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
        await this.checkWSReady()
        if (this.socket.readyState === WebSocket.OPEN) {
          this.socket.send(JSON.stringify({ reset: true }));
        } else {
            console.error('WebSocket is not in OPEN state');
        }
      },
      async startWebSocket() {
        this.socket = new WebSocket('ws://localhost:8000/audio'); // Connect to WebSocket server
        this.socket.onopen = () => {
          console.log('WebSocket connection established');
          // Start audio recording logic here
        };
        this.socket.onmessage = (event) => {
          const data = JSON.parse(event.data);
          // Handle incoming messages from the server

          this.transcript = data.message
          console.log(data.message);
        };
        this.socket.onerror = (error) => {
          console.error('WebSocket error:', error);
        };
        this.socket.onclose = () => {
          console.log('WebSocket connection closed');
        };
      },
      async checkWSReady() {
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
      }
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