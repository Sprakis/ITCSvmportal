let telegramApp = window.Telegram.WebApp;
document.querySelector('body').style.backgroundColor = telegramApp.themeParams.secondary_bg_color;
telegramApp.expand();
// telegramApp.MainButton.text = "Sign in";
// telegramApp.MainButton.color = "#ff0000";
// telegramApp.MainButton.show();

function togglePassword() {
	const passwordInput = document.getElementById('password');
	const showPasswordCheckbox = document.getElementById('show-password');
	if (showPasswordCheckbox.checked) {
		passwordInput.type = 'text';
	} else {
		passwordInput.type = 'password';
	}
}

document,getElementById('login-form').addEventListener('submit', function(event) {
	event.preventDefault();
	let username = document.getElementById('username').value;
	let password = document.getElementById('password').value;

	const creds = {
		login: username,
		pass: password
	};
	telegramApp.sendData(JSON.stringify(creds));
});