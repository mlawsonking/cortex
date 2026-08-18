import './lib/beacon.js';   // P6 bug loop: install the error listeners FIRST, before anything can throw
import './styles.css';
import { mount } from 'svelte';
import App from './App.svelte';

export default mount(App, { target: document.getElementById('app') });
