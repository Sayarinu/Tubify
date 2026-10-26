'use strict';
window.connectElgatoStreamDeckSocket = (port, uuid, registerEvent, info, actionInfo) => {
  const action = JSON.parse(actionInfo);
  const socket = new WebSocket(`ws://127.0.0.1:${Number(port)}`);
  const element = name => document.getElementById(name);
  const send = payload => { if (socket.readyState === 1) socket.send(JSON.stringify({event: 'sendToPlugin', action: action.action, context: action.context, payload})); };
  let shownOptions = "";
  socket.onopen = () => { socket.send(JSON.stringify({event: registerEvent, uuid})); send({operation: 'status'}); };
  socket.onmessage = event => {
    try {
      const message = JSON.parse(event.data);
      if (message.event !== 'sendToPropertyInspector') return;
      const value = message.payload;
      for (const name of ['status', 'detail', 'track', 'position']) element(name).textContent = value[name] || '';
      for (const name of ['pair', 'forget', 'reconnect']) element(name).disabled = !!value.busy;
      const options = JSON.stringify(value.options);
      if (options !== shownOptions) {
        shownOptions = options;
        for (const name of ['port', 'executable']) element(name).value = value.options[name];
      }
    } catch { element('status').textContent = 'Settings response unavailable.'; }
  };
  socket.onclose = () => { element('status').textContent = 'Stream Deck disconnected. Reopen these settings.'; };
  element('pairing').onsubmit = event => {
    event.preventDefault();
    const code = element('code').value.trim(); element('code').value = '';
    send({operation: 'pair', code, options: {port: Number(element('port').value), executable: element('executable').value}});
  };
  element('reconnect').onclick = () => send({operation: 'reconnect'});
  element('forget').onclick = () => send({operation: 'forget'});
};
