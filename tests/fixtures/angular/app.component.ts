import { Component, OnInit } from '@angular/core';
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';

@Injectable({ providedIn: 'root' })
export class UserService {
  constructor(private http: HttpClient) {}
  getUsers() { return this.http.get('/api/users'); }
}

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
})
export class AppComponent implements OnInit {
  users: any[] = [];
  constructor(private userService: UserService) {}
  ngOnInit() {
    this.userService.getUsers().subscribe((data: any) => this.users = data);
  }
}
