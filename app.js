const micButton = document.querySelector("#micButton");
const subtitle = document.querySelector(".stage__subtitle");

let isRecording = false;
let mediaRecorder;
let socket;
let mediaSource;
let sourceBuffer;
let pendingChunks = [];

const supportsStreamingAudio = () =>
  "MediaSource" in window && MediaSource.isTypeSupported("audio/mpeg");

const updateStatus = (text) => {
  subtitle.textContent = text;
};

const setupSocket = () => {
  socket = new WebSocket("ws://localhost:8000/ws");

  socket.addEventListener("message", async (event) => {
    const payload = JSON.parse(event.data);

    if (payload.type === "assistant_delta") {
      updateStatus(`Examiner: ${payload.text}`);
    }

    if (payload.type === "audio_chunk") {
      const binary = Uint8Array.from(atob(payload.data), (c) => c.charCodeAt(0));
      if (sourceBuffer && !sourceBuffer.updating) {
        sourceBuffer.appendBuffer(binary);
      } else {
        pendingChunks.push(binary);
      }
    }

    if (payload.type === "done") {
      updateStatus("Listening for your response...");
    }
  });

  socket.addEventListener("close", () => {
    updateStatus("Connection closed. Reload to reconnect.");
  });
};

const ensureAudioStream = () => {
  if (!supportsStreamingAudio()) {
    updateStatus("Your browser does not support streaming audio playback.");
    return;
  }

  mediaSource = new MediaSource();
  const audio = new Audio();
  audio.src = URL.createObjectURL(mediaSource);
  audio.play().catch(() => undefined);

  mediaSource.addEventListener("sourceopen", () => {
    sourceBuffer = mediaSource.addSourceBuffer("audio/mpeg");
    sourceBuffer.addEventListener("updateend", () => {
      if (pendingChunks.length > 0 && !sourceBuffer.updating) {
        sourceBuffer.appendBuffer(pendingChunks.shift());
      }
    });
  });
};

const startRecording = async () => {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    setupSocket();
    await new Promise((resolve) => {
      socket.addEventListener("open", resolve, { once: true });
    });
  }

  ensureAudioStream();
  updateStatus("Recording... Speak naturally.");

  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
  mediaRecorder.addEventListener("dataavailable", (event) => {
    if (event.data.size > 0 && socket.readyState === WebSocket.OPEN) {
      event.data.arrayBuffer().then((buffer) => socket.send(buffer));
    }
  });

  mediaRecorder.start(250);
  isRecording = true;
  micButton.classList.add("control--primary");
};

const stopRecording = () => {
  if (!mediaRecorder) return;
  mediaRecorder.stop();
  mediaRecorder.stream.getTracks().forEach((track) => track.stop());
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: "stop" }));
  }
  isRecording = false;
  micButton.classList.remove("control--primary");
  updateStatus("Processing your response...");
};

micButton.addEventListener("click", async () => {
  if (isRecording) {
    stopRecording();
  } else {
    try {
      await startRecording();
    } catch (error) {
      updateStatus("Microphone access denied.");
    }
  }
});

updateStatus("Tap the mic to begin speaking.");
