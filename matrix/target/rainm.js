// rain.js
const MATRIX_CHARS = [
  "- ", "* ", "% ", "& ", "# ", "@ ",
  "1 ", "2 ", "3 ", "4 ", "5 ", "6 ", "7 ", "8 ", "9 ", "0 ",
  "ア", "ィ", "イ", "ゥ", "ウ", "ェ", "エ", "ォ", "オ",
  "カ", "ガ", "キ", "ギ", "ク", "グ", "ケ", "ゲ", "コ", "ゴ",
  "サ", "ザ", "シ", "ジ", "ス", "ズ", "セ", "ゼ", "ソ", "ゾ",
  "タ", "ダ", "チ", "ヂ", "ッ", "ツ", "ヅ", "テ"
];
const TERMINAL_COLOURS = [22, 28];

class Matrix {
  constructor(screenWidth = 150, lineCount = 750, lineSpeed = 100) {
    this.screenWidth = screenWidth;
    this.lineCount = lineCount;
    this.lineSpeed = lineSpeed; // milliseconds (Python default 0.1s)
    this.lineArray = {};
  }

  lightGreen() {
    return "\x1b[38;5;15m";
  }

  randomGreen() {
    const colour = TERMINAL_COLOURS[Math.floor(Math.random() * 2)];
    return `\x1b[38;5;${colour}m`;
  }

  character() {
    return MATRIX_CHARS[Math.floor(Math.random() * MATRIX_CHARS.length)];
  }

  setScreenLineArray() {
    for (let i = 0; i < this.screenWidth; i++) {
      this.lineArray[i] = 1;
    }
  }

  startMatrix() {
    this.setScreenLineArray();
    let linesPrinted = 0;
    const timer = setInterval(() => {
      let line = "";
      for (const column of Object.keys(this.lineArray)) {
        const state = this.lineArray[column];
        if (state === 1 || state === 2) {
          if (state === 2) {
            line += this.lightGreen() + this.character();
            this.lineArray[column] = 1;
          } else {
            line += this.randomGreen() + this.character();
          }
          if (Math.floor(Math.random() * 30) + 1 === 1) {
            this.lineArray[column] = 0;
          }
        } else {
          line += this.randomGreen() + " ";
          if (Math.floor(Math.random() * 60) + 1 === 1) {
            this.lineArray[column] = 2;
          }
        }
      }
      console.log(line);
      linesPrinted++;
      if (linesPrinted >= this.lineCount) {
        clearInterval(timer);
      }
    }, this.lineSpeed);
  }
}

new Matrix().startMatrix();