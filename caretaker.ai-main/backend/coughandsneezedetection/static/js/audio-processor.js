/**
 * AudioWorklet Processor — high-performance background thread.
 *
 * Buffers raw PCM float32 samples and posts them to the main thread
 * in small batches for low-latency processing.
 *
 * Buffer size reduced to 2048 samples (~46ms @ 44.1kHz) for faster relay.
 */

class AudioChunkProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.buffer = [];
        this.bufferSize = 2048;  // Smaller = lower latency
    }

    process(inputs) {
        const input = inputs[0];
        if (!input || !input[0]) return true;

        const channelData = input[0];
        for (let i = 0; i < channelData.length; i++) {
            this.buffer.push(channelData[i]);
        }

        if (this.buffer.length >= this.bufferSize) {
            this.port.postMessage(new Float32Array(this.buffer));
            this.buffer = [];
        }

        return true;
    }
}

registerProcessor("audio-chunk-processor", AudioChunkProcessor);
