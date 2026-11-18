// Original short synth patches. Times are seconds, pitches and filter cutoffs are Hz.
function playTurn(ctx, bus, sounds) {
    function tone(at, wave, from, to, duration, level) {
        const osc = ctx.createOscillator();
        osc.type = wave;
        osc.frequency.setValueAtTime(from, at);
        osc.frequency.exponentialRampToValueAtTime(to, at + duration);
        envelope(osc, osc, at, duration, level);
    }

    function envelope(source, output, at, duration, level) {
        const amp = ctx.createGain();
        amp.gain.setValueAtTime(0.0001, at);
        amp.gain.exponentialRampToValueAtTime(level, at + 0.012);
        amp.gain.exponentialRampToValueAtTime(0.0001, at + duration);
        output.connect(amp);
        amp.connect(bus);
        source.onended = () => { source.disconnect(); output.disconnect(); amp.disconnect(); };
        source.start(at);
        source.stop(at + duration);
    }

    function rush(at, from, to, duration, level) {
        const samples = ctx.createBuffer(1, Math.ceil(ctx.sampleRate * duration), ctx.sampleRate);
        const data = samples.getChannelData(0);
        for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
        const noise = ctx.createBufferSource();
        noise.buffer = samples;
        const band = ctx.createBiquadFilter();
        band.type = "bandpass";
        band.Q.value = 1.2;
        band.frequency.setValueAtTime(from, at);
        band.frequency.exponentialRampToValueAtTime(to, at + duration);
        noise.connect(band);
        envelope(noise, band, at, duration, level);
    }

    sounds.forEach((name, index) => {
        const at = ctx.currentTime + 0.015 + index * 0.55;
        const notes = (pitches, step, length, wave, level) =>
            pitches.forEach((hz,i) => tone(at+i*step,wave,hz,hz,length,level));
        switch (name) {
            case "staff":
                rush(at, 900, 2800, .13, .65); tone(at+.10,"triangle",145,52,.16,.65); rush(at+.22,1600,360,.12,.45); break;
            case "funke":
                rush(at, 3600, 460, .28, .72); tone(at,"sawtooth",620,125,.23,.32); tone(at+.36,"triangle",134,42,.22,.68); break;
            case "frost":
                notes([2217,1865,2489,1245],.053,.22,"sine",.36); rush(at+.35,5700,1400,.26,.58); break;
            case "stern":
                notes([523,659,784,1047,1568],.055,.30,"triangle",.37); tone(at+.36,"sine",1047,2093,.43,.38); break;
            case "schild":
                tone(at,"sine",184,180,.55,.55); tone(at,"sine",493,440,.38,.40); break;
            case "ping":
                notes([880,880,880,1175],.09,.085,"sine",.46); break;
            case "kakao":
                [180,226,285].forEach((hz,i)=>tone(at+i*.09,"sine",hz,hz*1.6,.15,.44)); break;
            case "beeren":
                notes([587,880,740],.095,.15,"triangle",.50); break;
            case "disable":
                notes([440,330,220],.08,.075,"square",.22); break;
            case "frost_armor":
                tone(at,"square",155,52,.13,.30); rush(at+.08,3800,950,.34,.62); break;
            case "blizzard":
                rush(at,2100,95,.68,.88); break;
            case "loop":
                notes([262,392,523,784,1047,1568],.045,.26,"square",.27); break;
            case "ice_lock":
                tone(at,"sine",2800,700,.10,.32); rush(at+.03,4100,2400,.14,.38); break;
            case "parry":
                notes([940,1413],.025,.25,"triangle",.55); break;
            case "claw":
                rush(at,2200,240,.23,.78); tone(at+.07,"sawtooth",106,48,.24,.38); break;
            case "gale":
                rush(at,220,2600,.42,.92); tone(at+.16,"sawtooth",82,38,.44,.52);
                tone(at+.21,"triangle",117,54,.39,.46); break;
        }
    });
}
