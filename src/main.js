const youtubeMusicUrl = "https://music.youtube.com/";
const fallbackLink = document.querySelector("#fallback-link");

fallbackLink.href = youtubeMusicUrl;

window.setTimeout(() => {
  window.location.replace(youtubeMusicUrl);
}, 300);

window.setTimeout(() => {
  fallbackLink.classList.add("is-visible");
}, 1800);
