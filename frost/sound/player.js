const key = location.hash.slice(1);
const button = document.querySelector("button");
const statusText = document.querySelector("[role=status]");
let context, gain, buffer, source, volume;
let loading = false;
let effectBus;

function setLevel(value) {
    volume = value;
    if (gain) {
        gain.gain.setTargetAtTime((value / 100) ** 1.6, context.currentTime, 0.02);
    }
    statusText.textContent = value === 0 ? "Stumm" : "Lautstärke · " + value + " %";
}

function stop() {
    if (effectBus) { effectBus.disconnect(); effectBus = null; }
    if (source) {
        source.stop();
        source.disconnect();
        source = null;
    }
    button.textContent = "▶ Musik starten";
}

button.onclick = async () => {
    if (source) {
        stop();
        return;
    }
    loading = true;
    button.disabled = true;
    try {
        context ??= new AudioContext();
        await context.resume();
        if (!gain) {
            gain = context.createGain();
            gain.connect(context.destination);
        }
        if (!buffer) {
            const response = await fetch("/winter.wav");
            if (!response.ok) throw new Error("track unavailable");
            buffer = await context.decodeAudioData(await response.arrayBuffer());
        }
        if (volume === undefined) return;
        setLevel(volume);
        source = context.createBufferSource();
        source.buffer = buffer;
        source.loop = true;
        source.connect(gain);
        effectBus = context.createDynamicsCompressor();
        effectBus.connect(gain);
        source.start();
        button.textContent = "Ⅱ Pausieren";
    } catch {
        stop();
        statusText.textContent = "Audio konnte nicht starten. Bitte erneut versuchen.";
    } finally {
        loading = false;
        button.disabled = volume === undefined;
    }
};

function offline() {
    stop();
    volume = undefined;
    button.disabled = true;
    statusText.textContent = "Keine Verbindung. Öffne den aktuellen Link aus musik.";
}

if (/^[\w-]{16}$/.test(key)) {
    const events = new EventSource("/stream/" + key);
    events.onmessage = event => {
        const value = JSON.parse(event.data);
        if (value === null) {
            offline();
            return;
        }
        setLevel(value);
        button.disabled = loading;
    };
    events.addEventListener("attack", event => {
        if (source && effectBus && volume > 0) playTurn(context, effectBus, JSON.parse(event.data));
    });
    events.onerror = offline;
} else {
    statusText.textContent = "Gib im Spiel musik ein und öffne deinen persönlichen Link.";
}
