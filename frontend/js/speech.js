// frontend/js/speech.js

// Placeholder for speech synthesis functionality
const speech = {
    _isSpeaking: false,

    isSpeaking: () => {
        return speech._isSpeaking;
    },

    startSpeaking: () => {
        speech._isSpeaking = true;
        document.dispatchEvent(new CustomEvent('speech:start'));
        console.log("Speech synthesis started.");
        // Simulate speech ending after a delay for demonstration
        setTimeout(() => {
            speech.stop();
        }, 5000); 
    },

    stop: () => {
        speech._isSpeaking = false;
        document.dispatchEvent(new CustomEvent('speech:end'));
        console.log("Speech synthesis stopped.");
    }
};

// Expose speech object globally for direct access (e.g., from HTML attributes or other scripts)
window.speech = speech;

// Export for module-based imports
export { speech };
