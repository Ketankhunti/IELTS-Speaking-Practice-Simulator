const micButton = document.querySelector("#micButton");
const subtitle = document.querySelector(".stage__subtitle");

let isListening = true;

const updateStatus = () => {
  if (isListening) {
    subtitle.textContent = "Listening for your response...";
    micButton.classList.add("control--primary");
  } else {
    subtitle.textContent = "Paused. Tap the mic to continue.";
    micButton.classList.remove("control--primary");
  }
};

micButton.addEventListener("click", () => {
  isListening = !isListening;
  updateStatus();
});

updateStatus();
