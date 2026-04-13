package com.example.api.controller;

import org.springframework.web.bind.annotation.*;
import org.springframework.beans.factory.annotation.Autowired;
import com.example.api.service.UserService;
import com.example.api.entity.User;

/**
 * REST controller for user management.
 *
 * @see UserService
 * @see User
 */
@RestController
@RequestMapping("/api/users")
public class UserController {

    @Autowired
    private UserService userService;

    /**
     * Get all users.
     * @return list of users
     */
    @GetMapping
    public List<User> getAllUsers() {
        return userService.findAll();
    }

    /**
     * Get user by ID.
     * @param id user identifier
     * @return the user
     * @throws NotFoundException when user not found
     */
    @GetMapping("/{id}")
    public User getUser(@PathVariable Long id) {
        return userService.findById(id);
    }

    /** Create a new user. */
    @PostMapping
    public User createUser(@RequestBody User user) {
        return userService.save(user);
    }

    /** Update existing user. */
    @PutMapping("/{id}")
    public User updateUser(@PathVariable Long id, @RequestBody User user) {
        return userService.update(id, user);
    }

    /** Delete user. */
    @DeleteMapping("/{id}")
    public void deleteUser(@PathVariable Long id) {
        userService.delete(id);
    }
}
