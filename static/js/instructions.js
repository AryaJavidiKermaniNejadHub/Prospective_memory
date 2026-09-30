// Instruction texts. NOT original to Smith & Bayen (2006) - edit freely (plain HTML).
// Colour swatches: <span class="swatch c-red"></span>. Keys: <span class="kbd">Y</span>.
const sw = (...cs) => cs.map(c => `<span class="swatch c-${c}"></span>`).join('');
window.INSTR = {
  practice: `<h2>Welcome</h2>
    <p>In each trial you will see <b>four colored squares</b>, one after another. Then a <b>word</b> appears, printed in a color.</p>
    <div class="demo">${sw('red','blue','green','yellow')}<span class="word" style="color:var(--c-green)">EXAMPLE</span></div>
    <p>Your job: decide whether the <b>color of the word</b> (not what the word says) was one of the four squares you just saw.</p>
    <p>Press <span class="kbd">Y</span> for <b>YES</b>, the word's color matched one of the squares.<br>
    Press <span class="kbd">N</span> for <b>NO</b>, the word's color did not match any of the squares.</p>
    <p>In the example above the answer is <span class="kbd">Y</span> (green was shown). Respond quickly but accurately.</p>
    <p>First, a few <b>practice</b> trials. Only during practice you will be told when you make a mistake.</p>
    <button class="btn" id="next">Start practice</button>`,
  baseline: `<h2>Main task – Part 1</h2>
    <p>Now the real task begins. It works exactly like the practice, but <b>you will no longer receive any feedback</b>.</p>
    <p>Press <span class="kbd">Y</span> if the word's color matched one of the four squares, <span class="kbd">N</span> if not.</p>
    <p>On a phone, use the on-screen Y/N buttons. On a computer, you may use the keyboard.</p>
    <button class="btn" id="next">Start</button>`,
  training: `<h2>Part 2 – Words to remember</h2>
    <p>Next you will learn <b>six words</b>. They will be shown on the next screen. Study them carefully at your own pace.
    Afterwards you will be asked to type them from memory.</p>
    <button class="btn" id="next">Show the words</button>`,
  study: (words) => `<h2>Study these six words</h2><div class="words">${words.map(w => `<div>${w}</div>`).join('')}</div>
    <p>Press the button when you are ready to be tested.</p><button class="btn" id="next">I'm ready</button>`,
  recall: (n, attempt) => `<h2>Recall</h2><p>Type the ${n} words you just studied, in any order, one per box.</p>
    ${attempt > 1 ? '<p class="err">Not all words were correct. Please study the words again and try once more.</p>' : ''}<div id="boxes"></div>
    <button class="btn" id="next">Submit</button>`,
  restudy: `<h2>Study the words again</h2><p>You will see the six words once more, then be tested again.</p>
    <button class="btn" id="next">Show the words</button>`,
  breakScreen: `<h2>Break</h2><p>Please take a short break. <b>Keep this browser tab open.</b>
    The task will continue automatically when the timer ends.</p><p style="font-size:34px" id="timer"></p>
    <button class="btn" id="next" disabled>Continue</button>`,
  pm: `<h2>Main task – Part 2</h2>
    <p>The color-matching task continues exactly as before: press <span class="kbd">Y</span> or <span class="kbd">N</span> for the word's color. You can use the on-screen buttons on a phone.</p>
    <p><b>New:</b> Remember the six words you studied? Now, <b>whenever the word on the screen is one of those six words</b>,
    please <b>also</b> press <span class="kbd">Z</span>. This is <b>in addition to</b> your <span class="kbd">Y</span>/<span class="kbd">N</span> answer, never instead of it.</p>
    <div class="demo">${sw('red','blue','green','yellow')}<span class="word" style="color:var(--c-white)">EXAMPLE</span></div>
    <p>Say "EXAMPLE" were one of your six words: the correct responses would be <span class="kbd">N</span> (white was not shown)
    <b>and</b> <span class="kbd">Z</span>. You may press them in either order; press <span class="kbd">Z</span> right before, or right after
    your <span class="kbd">Y</span>/<span class="kbd">N</span> answer.</p>
    <p>On a phone, use the on-screen Y, N, and Z buttons.</p>
    <p>For all other words, just press <span class="kbd">Y</span> or <span class="kbd">N</span>. You will not receive feedback.</p>
    <button class="btn" id="next">Start</button>`,
  resume: `<h2>Continue</h2><p>Your session was resumed. Use the on-screen response buttons or keyboard.</p><button class="btn" id="next">Continue</button>`,
  ready: `<h2>Get ready</h2><p>Use the on-screen response buttons on a phone, or the keyboard on a computer.<br>Press the button (or the space bar) to begin.</p><button class="btn" id="next">Begin</button>`,
  done: `<h2>Thank you!</h2><p>You have completed the study. You may now close this window.</p>`,
};
