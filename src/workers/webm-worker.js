// Handle WebM muxing
const WEBM_HEADER = new Uint8Array([
  0x1a, 0x45, 0xdf, 0xa3, // EBML
  0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x20, // EBML size
  0x42, 0x86, 0x81, 0x01, // EBMLVersion
  0x42, 0xf7, 0x81, 0x01, // EBMLReadVersion
  0x42, 0xf2, 0x81, 0x04, // EBMLMaxIDLength
  0x42, 0xf3, 0x81, 0x08, // EBMLMaxSizeLength
  0x42, 0x82, 0x84, 0x77, 0x65, 0x62, 0x6d, // DocType "webm"
  0x42, 0x87, 0x81, 0x02, // DocTypeVersion
  0x42, 0x85, 0x81, 0x02  // DocTypeReadVersion
]);

self.onmessage = async function(e) {
  const chunk = e.data;
  if (!chunk) return;

  // Create a proper WebM chunk by adding headers
  const proper_chunk = new Blob([WEBM_HEADER, chunk], { type: 'audio/webm' });
  
  // Send back to main thread
  self.postMessage(proper_chunk);
}; 