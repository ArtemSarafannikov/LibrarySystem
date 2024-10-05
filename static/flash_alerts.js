function showAlert(message) {
    alert(message);
}


window.onload = function() {
    const flashMessages = JSON.parse(document.getElementById('flash-messages').textContent);

    flashMessages.forEach(function(message) {
            showAlert(message);
    });
};
