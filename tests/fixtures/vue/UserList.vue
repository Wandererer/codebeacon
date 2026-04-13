<template>
  <div>
    <h1>Users</h1>
    <ul>
      <li v-for="user in users" :key="user.id">{{ user.name }}</li>
    </ul>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, onMounted } from 'vue';

export default defineComponent({
  name: 'UserList',
  setup() {
    const users = ref([]);

    onMounted(async () => {
      const response = await fetch('/api/users');
      users.value = await response.json();
    });

    return { users };
  }
});
</script>
