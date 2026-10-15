<!-- Vista principal del inventario y tráfico obtenidos del router autorizado. -->
<script setup>
import Router from './components/Router.vue'
</script>

<template>
  <main>
    <header>
      <p class="ceja">Instalación local</p>
      <h1>Dispositivos de mi red</h1>
      <p>Consulta los dispositivos informados por tu router y el tráfico de sus interfaces WAN.</p>
    </header>
    <Router />
    <footer>Las muestras recientes se conservan temporalmente en memoria. No hay historial persistente.</footer>
  </main>
</template>
