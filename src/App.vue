<template>
    <v-app>
      <v-container fluid class="flex flex-col justify-between h-screen">
        <v-card class="overflow-y-auto flex-grow">
          <v-card-title>Chat</v-card-title>
          <v-card-text>
            <div class="flex flex-col">
              <!-- Stub for messages -->
              <div class="m-1 p-2 rounded bg-green-200 self-end">User message here</div>
              <div class="m-1 p-2 rounded bg-gray-200 self-start">Response message here</div>
              <!-- Add more message stubs as needed -->
            </div>
          </v-card-text>
        </v-card>
        <v-textarea
          v-model="textInput"
          label="Enter text to translate"
          @input="handleInput"
          class="mt-2"
        ></v-textarea>
        <div class="flex justify-center mt-2">
          <v-btn @click="toggleRecording" icon="mdi-microphone">
            <span v-if="isRecording">Recording...</span>
            <span v-else>Start Recording</span>
          </v-btn>
        </div>
        <div v-if="isRecording" class="mt-2">
          <div class="volume-bar" :style="{ width: volume + '%' }"></div>
        </div>
      </v-container>
    </v-app>
  </template>
  
<script>

import lamejs from 'lamejs';

import MPEGMode from 'lamejs/src/js/MPEGMode';
import Lame from 'lamejs/src/js/Lame';
import BitStream from 'lamejs/src/js/BitStream';


window.MPEGMode = MPEGMode;
window.Lame = Lame;
window.BitStream = BitStream;
  
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
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          this.mediaRecorder = new MediaRecorder(stream, { 
            mimeType: 'audio/webm' ,
            audioBitsPerSecond: 128000
        });
          
          // Set up audio context and analyser
          this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
          this.analyser = this.audioContext.createAnalyser();
          this.microphone = this.audioContext.createMediaStreamSource(stream);
          this.microphone.connect(this.analyser);
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

                const url = window.URL.createObjectURL(audioBlob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                a.download = `audio-${Date.now()}.webm`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);

                console.log(audioBlob)
                await this.sendAudio(audioBlob);
            }
          };

          this.mediaRecorder.onstart = () => {
            console.log('Recording started');
            updateVolume(); // Start updating the volume
          };

          this.mediaRecorder.onstop = () => {
            this.audioContext.close(); // Close the audio context
            console.log('Recording stopped');
          };

          this.mediaRecorder.start(3000); // Start recording with a timeslice of 100ms
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
        if (!this.socket?.readyState !== WebSocket.OPEN) {
            await this.startWebSocket();
            await new Promise(r => setTimeout(r, 100)); // Simple wait for connection
        }
        this.socket.send(audioBlob);
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
          console.log(data.message);
        };
        this.socket.onerror = (error) => {
          console.error('WebSocket error:', error);
        };
        this.socket.onclose = () => {
          console.log('WebSocket connection closed');
        };
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