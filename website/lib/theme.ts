export const themeKey = 'solveguide-website-theme'
export type Theme = 'dark' | 'light' | 'system'
// Kept as one bootstrap source for pre-paint application and focused regression tests.
export const themeBootstrap = `(function(){var t='system';try{var v=localStorage.getItem('${themeKey}');if(v==='dark'||v==='light'||v==='system')t=v}catch{}document.documentElement.dataset.theme=t==='system'?(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'):t})()`
