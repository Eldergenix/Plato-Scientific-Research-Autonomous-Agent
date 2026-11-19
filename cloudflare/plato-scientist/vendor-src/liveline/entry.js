// window.LivelineKit.mount(el, props) renders <Liveline {...props}/> into el and returns
// { update(props), unmount() }. React stays inside this bundle; the app never sees it.
import { createElement } from "react";
import { createRoot } from "react-dom/client";
import { Liveline } from "liveline";

function mount(el, props) {
  const root = createRoot(el);
  root.render(createElement(Liveline, props));
  return {
    update(next) { root.render(createElement(Liveline, next)); },
    unmount() { root.unmount(); },
  };
}

window.LivelineKit = Object.freeze({ mount, version: "0.0.7" });
