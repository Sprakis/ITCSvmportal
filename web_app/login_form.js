function start_func() {
	let telegramApp = window.Telegram.WebApp;
	document.querySelector('body').style.backgroundColor = telegramApp.themeParams.secondary_bg_color;
	telegramApp.expand();
	telegramApp.MainButton.text = "Sign in";
	telegramApp.MainButton.color = "#ff0000";
	telegramApp.MainButton.show();

	function send() {
		let login = document.getElementById('username').value;
		let pass = document.getElementById('password').value;
		let creds = '{\n\t"login": "' + login + '",\n\t"pass": "' + pass + '"\n}';
		telegramApp.sendData(creds);
		console.log("send_by_click")
	}

	telegramApp.MainButton.onClick(send())
};
