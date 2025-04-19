function togglePassword() {
	const passwordInput = document.getElementById('password');
	const eyeIcon = document.getElementById('eye-icon');
	if (passwordInput.type === 'password') {
		passwordInput.type = 'text';
		eyeIcon.classList.remove('fa-eye');
		eyeIcon.classList.add('fa-eye-slash');
	} else {
		passwordInput.type = 'password';
		eyeIcon.classList.remove('fa-eye-slash');
		eyeIcon.classList.add('fa-eye');
	}
};

function start_func() {
	let telegramApp = window.Telegram.WebApp;
	document.querySelector('body').style.backgroundColor = telegramApp.themeParams.secondary_bg_color;
	telegramApp.expand();	

	document.getElementById('login-form').addEventListener('submit', function(event) {
		event.preventDefault();
		let username = document.getElementById('username').value;
		let password = document.getElementById('password').value;
	
		const creds = {
			login: username,
			pass: password
		};
		telegramApp.sendData(JSON.stringify(creds));
	});
}