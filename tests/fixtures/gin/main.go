package main

import "github.com/gin-gonic/gin"

type User struct {
    ID   uint   `json:"id" gorm:"primaryKey"`
    Name string `json:"name"`
}

func main() {
    r := gin.Default()

    r.GET("/users", func(c *gin.Context) {
        c.JSON(200, []User{})
    })

    r.GET("/users/:id", func(c *gin.Context) {
        c.JSON(200, gin.H{"id": c.Param("id")})
    })

    r.POST("/users", func(c *gin.Context) {
        var user User
        c.BindJSON(&user)
        c.JSON(201, user)
    })

    r.PUT("/users/:id", func(c *gin.Context) {
        c.JSON(200, gin.H{"updated": c.Param("id")})
    })

    r.DELETE("/users/:id", func(c *gin.Context) {
        c.JSON(200, gin.H{"deleted": c.Param("id")})
    })

    r.Run(":8080")
}
