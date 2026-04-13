<script lang="ts">
  import { onMount } from 'svelte';
  export let data: { users: any[] } = { users: [] };

  onMount(async () => {
    const res = await fetch('/api/users');
    data.users = await res.json();
  });
</script>

<h1>Users</h1>
<ul>
  {#each data.users as user}
    <li>{user.name}</li>
  {/each}
</ul>
