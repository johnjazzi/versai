<template>
    <div>
     <v-progress-linear 
        height="16"
        color="blue"
        model-value="percentage" >
        <strong>{{ text }} ({{ percentage.toFixed(2) }}%{{ total ? ` of ${formatBytes(total)}` : '' }})</strong> 
      </v-progress-linear>
    </div>
  </template>
  
  <script>
  export default {
    props: {
      text: String,
      percentage: Number,
      total: Number
    },
    methods: {
      formatBytes(size) {
        const i = size == 0 ? 0 : Math.floor(Math.log(size) / Math.log(1024));
        return +((size / Math.pow(1024, i)).toFixed(2)) + ' ' + ['B', 'kB', 'MB', 'GB', 'TB'][i];
      }
    }
  };
  </script>